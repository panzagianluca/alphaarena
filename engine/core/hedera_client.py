"""
Hedera blockchain client for Agent League.

Handles:
- Wallet pool management (assign wallets to agents)
- HTS token transfers (airdrop ARENA, buy/sell wrapped assets)
- HCS message publishing (price oracle + trade reasoning)
- Transaction sequencing (asyncio.Lock for treasury-signed txs)

Uses hiero-sdk-python directly for programmatic operations.
Falls back to STUB mode (logging only) when the SDK is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import the Hedera SDK.  If unavailable, we run in stub mode.
# ---------------------------------------------------------------------------

_SDK_AVAILABLE = False
try:
    from hiero_sdk_python import (  # type: ignore[import-untyped]
        AccountId,
        Client,
        Hbar,
        Network,
        PrivateKey,
        TokenId,
        TopicId,
        TopicMessageSubmitTransaction,
        TransferTransaction,
    )

    _SDK_AVAILABLE = True
    logger.info("hiero_sdk_python loaded - running in LIVE mode")
except ImportError:
    logger.warning(
        "hiero_sdk_python not available - running in STUB mode "
        "(transactions will be logged but not submitted)"
    )

TOKEN_DECIMALS = 6
_UNIT_MULTIPLIER = 10 ** TOKEN_DECIMALS

# ---------------------------------------------------------------------------
# Asset -> wrapped-token-name mapping
# ---------------------------------------------------------------------------

_ASSET_TO_WRAPPED: dict[str, str] = {
    "HBAR": "wHBAR",
    "BTC": "wBTC",
    "ETH": "wETH",
    "DOGE": "wDOGE",
}


class HederaClient:
    """Hedera testnet client — manages wallets, HTS transfers, and HCS messages.

    When the SDK is not installed the client operates in **stub mode**:
    every method logs what it *would* do and returns ``None`` for tx IDs.
    The rest of the engine works fine with ``tx_id=None``.
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        # Treasury credentials (graceful fallback for stub mode)
        self.treasury_account_id: str = os.environ.get("HEDERA_ACCOUNT_ID", "0.0.0")
        self.treasury_private_key: str = os.environ.get("HEDERA_PRIVATE_KEY", "stub")

        # Wallet pool
        wallet_path = os.environ.get("WALLET_POOL_PATH", "./wallets.json")
        wp = Path(wallet_path)
        if not wp.exists():
            raise FileNotFoundError(f"Wallet pool not found at {wp}")
        self._wallet_pool: list[dict[str, Any]] = json.loads(wp.read_text())
        self._wallet_path = wp

        # Token IDs
        self.token_ids: dict[str, str] = {
            "ARENA": os.environ.get("TOKEN_ARENA_ID", ""),
            "wHBAR": os.environ.get("TOKEN_WHBAR_ID", ""),
            "wBTC": os.environ.get("TOKEN_WBTC_ID", ""),
            "wETH": os.environ.get("TOKEN_WETH_ID", ""),
            "wDOGE": os.environ.get("TOKEN_WDOGE_ID", ""),
        }

        # HCS Topic IDs
        self.hcs_price_topic_id: str = os.environ.get("HCS_PRICE_TOPIC_ID", "")
        self.hcs_trades_topic_id: str = os.environ.get("HCS_TRADES_TOPIC_ID", "")

        # Transaction lock — serializes treasury-signed transactions
        self._tx_lock = asyncio.Lock()

        # Per-agent client cache (for agent-signed sell transactions)
        self._agent_clients: dict[str, Any] = {}

        # SDK client (treasury)
        self._sdk_client: Any = None
        self.stub_mode: bool = not _SDK_AVAILABLE

        if _SDK_AVAILABLE:
            try:
                self._sdk_client = Client(Network(network="testnet"))
                key_hex = self.treasury_private_key.removeprefix("0x")
                self._treasury_key = PrivateKey.from_bytes_ecdsa(bytes.fromhex(key_hex))
                self._treasury_account = AccountId.from_string(self.treasury_account_id)
                self._sdk_client.set_operator(self._treasury_account, self._treasury_key)
                logger.info("Hedera SDK client initialized (treasury=%s)", self.treasury_account_id)
            except Exception:
                logger.exception("Failed to init Hedera SDK client, falling back to stub mode")
                self.stub_mode = True

    # ------------------------------------------------------------------
    # Wallet Assignment
    # ------------------------------------------------------------------

    def assign_wallet(self) -> dict[str, Any]:
        """Find the next unassigned wallet, mark it assigned, persist, and return it.

        Returns dict with keys: ``index``, ``account_id``, ``private_key``.
        Raises ``RuntimeError`` if the pool is exhausted.
        """
        for wallet in self._wallet_pool:
            if not wallet["assigned"]:
                wallet["assigned"] = True
                self._persist_wallet_pool()
                return {
                    "index": wallet["index"],
                    "account_id": wallet["account_id"],
                    "private_key": wallet["private_key"],
                }
        raise RuntimeError("No available wallets in pool — all assigned")

    def _persist_wallet_pool(self) -> None:
        """Write current wallet pool state back to disk."""
        self._wallet_path.write_text(json.dumps(self._wallet_pool, indent=2))

    # ------------------------------------------------------------------
    # Token ID helpers
    # ------------------------------------------------------------------

    def _get_token_id_for_asset(self, asset: str) -> str:
        """Map a trading asset symbol (BTC, ETH, ...) to its wrapped HTS token ID."""
        wrapped = _ASSET_TO_WRAPPED.get(asset)
        if wrapped is None:
            raise KeyError(f"Unknown asset: {asset}")
        token_id = self.token_ids.get(wrapped, "")
        if not token_id:
            raise KeyError(f"No token ID configured for {wrapped}")
        return token_id

    # ------------------------------------------------------------------
    # Agent Client Caching
    # ------------------------------------------------------------------

    def _get_agent_client(self, account_id: str, private_key: str) -> Any:
        """Lazily create and cache a Hedera Client for an agent wallet.

        Used for agent-signed transactions (sells). Different account =
        different nonce space = no conflict with treasury.
        """
        if account_id not in self._agent_clients:
            if _SDK_AVAILABLE:
                agent_client = Client(Network(network="testnet"))
                key_hex = private_key.removeprefix("0x")
                agent_key = PrivateKey.from_bytes_ecdsa(bytes.fromhex(key_hex))
                agent_client.set_operator(
                    AccountId.from_string(account_id),
                    agent_key,
                )
                self._agent_clients[account_id] = agent_client
            else:
                # Stub: store a marker dict so caching works
                self._agent_clients[account_id] = {
                    "account_id": account_id,
                    "stub": True,
                }
        return self._agent_clients[account_id]

    # ------------------------------------------------------------------
    # Low-level SDK operations (overridable for testing)
    # ------------------------------------------------------------------

    async def _do_fund_agent(self, agent_account_id: str, amount: int) -> str | None:
        """Airdrop ARENA tokens from treasury to agent. Returns tx_id or None."""
        if self.stub_mode:
            logger.info(
                "STUB: Would airdrop %d ARENA from treasury(%s) to %s",
                amount, self.treasury_account_id, agent_account_id,
            )
            return None

        arena_token = TokenId.from_string(self.token_ids["ARENA"])
        receiver = AccountId.from_string(agent_account_id)
        base_amount = int(amount * _UNIT_MULTIPLIER)

        def _execute():
            tx = (
                TransferTransaction()
                .add_token_transfer(arena_token, self._treasury_account, -base_amount)
                .add_token_transfer(arena_token, receiver, base_amount)
                .freeze_with(self._sdk_client)
                .sign(self._treasury_key)
            )
            return tx.execute(self._sdk_client)

        receipt = await asyncio.to_thread(_execute)
        tx_id = str(receipt.transaction_id)
        logger.info("Funded agent %s with %d ARENA: %s", agent_account_id, amount, tx_id)
        return tx_id

    async def _do_treasury_airdrop(
        self, token_id: str, agent_account_id: str, amount: float, label: str = "",
    ) -> str | None:
        """Airdrop a wrapped asset token from treasury to agent. Returns tx_id or None."""
        if self.stub_mode:
            logger.info(
                "STUB: Would airdrop %.6f %s (token %s) from treasury to %s",
                amount, label, token_id, agent_account_id,
            )
            return None

        token = TokenId.from_string(token_id)
        receiver = AccountId.from_string(agent_account_id)
        base_amount = int(amount * _UNIT_MULTIPLIER)

        def _execute():
            tx = (
                TransferTransaction()
                .add_token_transfer(token, self._treasury_account, -base_amount)
                .add_token_transfer(token, receiver, base_amount)
                .freeze_with(self._sdk_client)
                .sign(self._treasury_key)
            )
            return tx.execute(self._sdk_client)

        receipt = await asyncio.to_thread(_execute)
        tx_id = str(receipt.transaction_id)
        logger.info("Treasury airdrop %.6f %s to %s: %s", amount, label, agent_account_id, tx_id)
        return tx_id

    async def _do_agent_send(
        self,
        token_id: str,
        agent_account_id: str,
        agent_private_key: str,
        amount: float,
        label: str = "",
    ) -> str | None:
        """Agent sends wrapped token back to treasury. Returns tx_id or None."""
        if self.stub_mode:
            logger.info(
                "STUB: Would send %.6f %s (token %s) from %s back to treasury",
                amount, label, token_id, agent_account_id,
            )
            return None

        agent_client = self._get_agent_client(agent_account_id, agent_private_key)
        token = TokenId.from_string(token_id)
        sender = AccountId.from_string(agent_account_id)
        key_hex = agent_private_key.removeprefix("0x")
        agent_key = PrivateKey.from_bytes_ecdsa(bytes.fromhex(key_hex))
        base_amount = int(amount * _UNIT_MULTIPLIER)

        def _execute():
            tx = (
                TransferTransaction()
                .add_token_transfer(token, sender, -base_amount)
                .add_token_transfer(token, self._treasury_account, base_amount)
                .freeze_with(agent_client)
                .sign(agent_key)
            )
            return tx.execute(agent_client)

        receipt = await asyncio.to_thread(_execute)
        tx_id = str(receipt.transaction_id)
        logger.info("Agent %s sent %.6f %s to treasury: %s", agent_account_id, amount, label, tx_id)
        return tx_id

    async def _do_publish_hcs(self, topic_id: str, message: str) -> str | None:
        """Publish a message to an HCS topic. Returns tx_id or None."""
        if self.stub_mode:
            logger.info("STUB: Would publish to HCS topic %s: %s", topic_id, message[:120])
            return None

        topic = TopicId.from_string(topic_id)

        def _execute():
            tx = (
                TopicMessageSubmitTransaction()
                .set_topic_id(topic)
                .set_message(message)
                .freeze_with(self._sdk_client)
                .sign(self._treasury_key)
            )
            return tx.execute(self._sdk_client)

        receipt = await asyncio.to_thread(_execute)
        tx_id = str(receipt.transaction_id)
        logger.info("Published to HCS %s: %s", topic_id, tx_id)
        return tx_id

    # ------------------------------------------------------------------
    # Public API: Fund Agent
    # ------------------------------------------------------------------

    async def fund_agent(self, agent_account_id: str, amount: int) -> str | None:
        """Airdrop ARENA tokens from treasury to agent.

        Uses the transaction lock to serialize treasury-signed operations.
        Returns tx_id or None on failure.
        """
        try:
            async with self._tx_lock:
                return await self._do_fund_agent(agent_account_id, amount)
        except Exception:
            logger.exception("Failed to fund agent %s with %d ARENA", agent_account_id, amount)
            return None

    # ------------------------------------------------------------------
    # Public API: Execute Trade
    # ------------------------------------------------------------------

    async def execute_trade(
        self,
        action: str,
        asset: str,
        amount_tokens: float,
        agent_account_id: str,
        agent_private_key: str,
        sell_arena_value: float = 0.0,
    ) -> str | None:
        """Execute an on-chain trade.

        - **BUY**: Treasury airdrops wrapped asset token to agent (treasury signs).
        - **SELL**: Agent sends wrapped asset back to treasury (agent signs)
          + treasury airdrops ARENA back to agent (treasury signs).
        - **HOLD**: No transaction, returns None.

        Returns tx_id or None on failure.
        """
        if action == "hold":
            return None

        try:
            if action == "buy":
                token_id = self._get_token_id_for_asset(asset)
                wrapped_name = _ASSET_TO_WRAPPED[asset]
                logger.info(
                    "BUY: Airdropping %.6f %s to %s",
                    amount_tokens, wrapped_name, agent_account_id,
                )
                async with self._tx_lock:
                    return await self._do_treasury_airdrop(
                        token_id, agent_account_id, amount_tokens, label=wrapped_name,
                    )

            elif action == "sell":
                token_id = self._get_token_id_for_asset(asset)
                wrapped_name = _ASSET_TO_WRAPPED[asset]
                logger.info(
                    "SELL: %s returning %.6f %s to treasury + receiving ARENA",
                    agent_account_id, amount_tokens, wrapped_name,
                )

                send_tx = None
                # Step 1: Agent sends wrapped token back (only if key is valid hex)
                if agent_private_key and not agent_private_key.startswith("stub_"):
                    send_tx = await self._do_agent_send(
                        token_id, agent_account_id, agent_private_key,
                        amount_tokens, label=wrapped_name,
                    )

                # Step 2: Treasury airdrops ARENA back to agent
                arena_amount = sell_arena_value if sell_arena_value > 0 else amount_tokens
                async with self._tx_lock:
                    arena_tx = await self._do_treasury_airdrop(
                        self.token_ids["ARENA"], agent_account_id,
                        arena_amount, label="ARENA",
                    )

                # Return whichever tx_id we got
                return send_tx or arena_tx

            else:
                logger.warning("Unknown trade action: %s", action)
                return None

        except Exception:
            logger.exception(
                "Failed to execute trade: %s %s %.4f for %s",
                action, asset, amount_tokens, agent_account_id,
            )
            return None

    # ------------------------------------------------------------------
    # Public API: HCS Publishing
    # ------------------------------------------------------------------

    async def publish_prices(
        self, prices: dict[str, Any], round_number: int,
    ) -> str | None:
        """Publish current round's price data to the HCS price oracle topic.

        Returns tx_id or None on failure.
        """
        message = json.dumps({
            "round": round_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prices": prices,
        })
        try:
            async with self._tx_lock:
                logger.info("Publishing prices to HCS (round %d)", round_number)
                return await self._do_publish_hcs(self.hcs_price_topic_id, message)
        except Exception:
            logger.exception("Failed to publish prices for round %d", round_number)
            return None

    async def publish_trade_reasoning(
        self,
        agent_name: str,
        round_number: int,
        decision: dict[str, Any],
        hedera_tx_id: str | None,
    ) -> str | None:
        """Publish trade decision + reasoning to the HCS trade reasoning topic.

        Returns tx_id or None on failure.
        """
        message = json.dumps({
            "agent": agent_name,
            "round": round_number,
            "action": decision.get("action", "hold"),
            "asset": decision.get("asset", "NONE"),
            "amount_pct": decision.get("amount_pct", 0),
            "reasoning": decision.get("reasoning", ""),
            "confidence": decision.get("confidence", 0),
            "hedera_tx_id": hedera_tx_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        try:
            async with self._tx_lock:
                logger.info(
                    "Publishing trade reasoning to HCS for %s (round %d)",
                    agent_name, round_number,
                )
                return await self._do_publish_hcs(self.hcs_trades_topic_id, message)
        except Exception:
            logger.exception(
                "Failed to publish reasoning for %s round %d", agent_name, round_number,
            )
            return None

    # ------------------------------------------------------------------
    # Public API: Capital Allocation
    # ------------------------------------------------------------------

    async def allocate_capital(
        self, agent_account_id: str, amount: int,
    ) -> str | None:
        """Send ARENA from treasury to agent (capital allocation).

        Uses the transaction lock. Returns tx_id or None on failure.
        """
        logger.info("Allocating %d ARENA to %s", amount, agent_account_id)
        try:
            async with self._tx_lock:
                return await self._do_fund_agent(agent_account_id, amount)
        except Exception:
            logger.exception(
                "Failed to allocate %d ARENA to %s", amount, agent_account_id,
            )
            return None

    # ------------------------------------------------------------------
    # Public API: User-to-Agent Transfer
    # ------------------------------------------------------------------

    async def transfer_user_to_agent(
        self,
        user_account_id: str,
        user_private_key: str,
        agent_account_id: str,
        amount: int,
    ) -> str | None:
        """Transfer ARENA from user wallet to agent wallet. User-signed transaction."""
        if self.stub_mode:
            logger.info(
                "STUB: Would transfer %d ARENA from user %s to agent %s",
                amount, user_account_id, agent_account_id,
            )
            return None

        try:
            arena_token = TokenId.from_string(self.token_ids["ARENA"])
            sender = AccountId.from_string(user_account_id)
            receiver = AccountId.from_string(agent_account_id)
            user_client = self._get_agent_client(user_account_id, user_private_key)
            key_hex = user_private_key.removeprefix("0x")
            user_key = PrivateKey.from_bytes_ecdsa(bytes.fromhex(key_hex))
            base_amount = int(amount * _UNIT_MULTIPLIER)

            def _execute():
                tx = (
                    TransferTransaction()
                    .add_token_transfer(arena_token, sender, -base_amount)
                    .add_token_transfer(arena_token, receiver, base_amount)
                    .freeze_with(user_client)
                    .sign(user_key)
                )
                return tx.execute(user_client)

            receipt = await asyncio.to_thread(_execute)
            tx_id = str(receipt.transaction_id)
            logger.info(
                "User %s transferred %d ARENA to agent %s: %s",
                user_account_id, amount, agent_account_id, tx_id,
            )
            return tx_id
        except Exception as e:
            logger.error("User transfer failed: %s", e)
            return None


# ---------------------------------------------------------------------------
# CLI: Introspection + smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=== Hedera Client Introspection ===\n")

    # 1. Check what's importable from hiero_sdk_python
    print("--- hiero_sdk_python availability ---")
    try:
        import hiero_sdk_python  # type: ignore[import-untyped]

        members = sorted(dir(hiero_sdk_python))
        print(f"SDK loaded! {len(members)} exports:")
        for m in members:
            if not m.startswith("_"):
                print(f"  {m}")
    except ImportError:
        print("hiero_sdk_python NOT installed — stub mode only")

    # 2. Check env vars
    print("\n--- Environment ---")
    for key in [
        "HEDERA_ACCOUNT_ID", "HEDERA_PRIVATE_KEY", "WALLET_POOL_PATH",
        "TOKEN_ARENA_ID", "TOKEN_WHBAR_ID", "TOKEN_WBTC_ID",
        "TOKEN_WETH_ID", "TOKEN_WDOGE_ID",
        "HCS_PRICE_TOPIC_ID", "HCS_TRADES_TOPIC_ID",
    ]:
        val = os.environ.get(key, "")
        masked = val[:8] + "..." if len(val) > 12 else val
        status = "SET" if val else "MISSING"
        print(f"  {key}: {status} ({masked})")

    # 3. Try basic init
    print("\n--- Client Init ---")
    try:
        client = HederaClient()
        print(f"  stub_mode: {client.stub_mode}")
        print(f"  treasury: {client.treasury_account_id}")
        print(f"  wallets: {len(client._wallet_pool)} in pool")
        unassigned = sum(1 for w in client._wallet_pool if not w["assigned"])
        print(f"  available: {unassigned}")
        print(f"  tokens: {client.token_ids}")
        print(f"  topics: price={client.hcs_price_topic_id}, trades={client.hcs_trades_topic_id}")
    except Exception as exc:
        print(f"  FAILED: {exc}")

    print("\nDone.")
