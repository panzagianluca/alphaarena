"""
One-time Hedera testnet setup for Agent League.

Creates:
- 15 agent accounts (with max_automatic_token_associations=-1)
- 5 HTS tokens (ARENA, wHBAR, wBTC, wETH, wDOGE) with 6 decimals
- 2 HCS topics (price oracle, trade reasoning)

Writes credentials to wallets.json and prints env vars for .env.

Usage:
    python -m engine.scripts.setup_hedera

Requires:
    - HEDERA_ACCOUNT_ID and HEDERA_PRIVATE_KEY set in environment
    - hiero-sdk-python installed
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Try to import the SDK
# ---------------------------------------------------------------------------

_SDK_AVAILABLE = False
try:
    from hiero_sdk_python import (  # type: ignore[import-untyped]
        AccountCreateTransaction,
        AccountId,
        Client,
        Hbar,
        Network,
        PrivateKey,
        TokenCreateTransaction,
        TokenType,
        SupplyType,
        TopicCreateTransaction,
    )

    _SDK_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NUM_ACCOUNTS = 15
TOKEN_DECIMALS = 6
TOKEN_INITIAL_SUPPLY = 1_000_000  # in whole units; smallest unit = supply * 10^decimals

TOKENS_TO_CREATE = [
    ("ARENA", "ARENA"),
    ("wHBAR", "wHBAR"),
    ("wBTC", "wBTC"),
    ("wETH", "wETH"),
    ("wDOGE", "wDOGE"),
]

TOPICS_TO_CREATE = [
    "Agent League - Price Oracle",
    "Agent League - Trade Decisions",
]


def run_stub() -> None:
    """Generate stub wallets.json for local development without Hedera."""
    print("=== STUB MODE (hiero-sdk-python not installed) ===\n")
    print("Generating fake wallets.json for local dev...\n")

    wallets = []
    for i in range(NUM_ACCOUNTS):
        wallets.append({
            "index": i,
            "account_id": f"0.0.{4000 + i}",
            "private_key": f"302e020100300506032b657004220420{'%04x' % i}" * 4,
            "assigned": False,
        })

    output_path = Path("wallets.json")
    output_path.write_text(json.dumps(wallets, indent=2))
    print(f"Wrote {len(wallets)} stub wallets to {output_path}")

    print("\n--- Stub Token IDs (paste into .env) ---")
    for name, symbol in TOKENS_TO_CREATE:
        print(f"TOKEN_{name}_ID=0.0.{7000 + TOKENS_TO_CREATE.index((name, symbol))}")
    print("HCS_PRICE_TOPIC_ID=0.0.8001")
    print("HCS_TRADES_TOPIC_ID=0.0.8002")
    print("\nDone (stub mode).")


def run_live() -> None:
    """Create real accounts, tokens, and topics on Hedera testnet."""
    account_id = os.environ.get("HEDERA_ACCOUNT_ID", "")
    private_key_hex = os.environ.get("HEDERA_PRIVATE_KEY", "").removeprefix("0x")

    if not account_id or not private_key_hex:
        print("ERROR: Set HEDERA_ACCOUNT_ID and HEDERA_PRIVATE_KEY in environment.")
        sys.exit(1)

    print("=== LIVE MODE (hiero-sdk-python) ===\n")
    print(f"Treasury: {account_id}")

    # Connect — ECDSA key (EVM-compatible account)
    client = Client(Network(network="testnet"))
    operator_account = AccountId.from_string(account_id)
    operator_key = PrivateKey.from_bytes_ecdsa(bytes.fromhex(private_key_hex))
    client.set_operator(operator_account, operator_key)
    print("Connected to testnet (ECDSA key).\n")

    # --- 1. Create agent accounts ---
    print(f"Creating {NUM_ACCOUNTS} agent accounts...")
    wallets = []
    for i in range(NUM_ACCOUNTS):
        try:
            agent_key = PrivateKey.generate_ecdsa()
            tx = (
                AccountCreateTransaction()
                .set_key(agent_key.public_key())
                .set_initial_balance(Hbar(2))
                .set_max_automatic_token_associations(-1)
                .set_account_memo(f"Agent League Wallet #{i}")
                .freeze_with(client)
                .sign(operator_key)
            )
            receipt = tx.execute(client)
            wallets.append({
                "index": i,
                "account_id": str(receipt.account_id),
                "private_key": agent_key.to_bytes_raw().hex(),
                "assigned": False,
            })
            print(f"  Account {i}: {receipt.account_id}")
        except Exception as exc:
            print(f"  Account {i}: FAILED ({exc})")
            wallets.append({
                "index": i,
                "account_id": "",
                "private_key": "",
                "assigned": False,
                "error": str(exc),
            })

    # --- 2. Create HTS tokens ---
    print(f"\nCreating {len(TOKENS_TO_CREATE)} HTS tokens...")
    token_ids: dict[str, str] = {}
    for name, symbol in TOKENS_TO_CREATE:
        try:
            tx = (
                TokenCreateTransaction()
                .set_token_name(f"Agent League {name}")
                .set_token_symbol(symbol)
                .set_decimals(TOKEN_DECIMALS)
                .set_initial_supply(TOKEN_INITIAL_SUPPLY * (10 ** TOKEN_DECIMALS))
                .set_token_type(TokenType.FUNGIBLE_COMMON)
                .set_supply_type(SupplyType.INFINITE)
                .set_treasury_account_id(operator_account)
                .set_supply_key(operator_key.public_key())
                .freeze_with(client)
                .sign(operator_key)
            )
            receipt = tx.execute(client)
            token_ids[name] = str(receipt.token_id)
            print(f"  {name}: {receipt.token_id}")
        except Exception as exc:
            print(f"  {name}: FAILED ({exc})")
            token_ids[name] = ""

    # --- 3. Create HCS topics ---
    print(f"\nCreating {len(TOPICS_TO_CREATE)} HCS topics...")
    topic_ids: list[str] = []
    for memo in TOPICS_TO_CREATE:
        try:
            tx = (
                TopicCreateTransaction()
                .set_memo(memo)
                .freeze_with(client)
                .sign(operator_key)
            )
            receipt = tx.execute(client)
            tid = str(receipt.topic_id)
            topic_ids.append(tid)
            print(f"  {memo}: {tid}")
        except Exception as exc:
            print(f"  {memo}: FAILED ({exc})")
            topic_ids.append("")

    # --- 4. Write wallets.json ---
    output_path = Path("wallets.json")
    output_path.write_text(json.dumps(wallets, indent=2))
    print(f"\nWrote {len(wallets)} wallets to {output_path}")

    # --- 5. Print env vars ---
    print("\n--- Paste into .env ---")
    for name, _ in TOKENS_TO_CREATE:
        print(f"TOKEN_{name}_ID={token_ids.get(name, '')}")
    if len(topic_ids) >= 2:
        print(f"HCS_PRICE_TOPIC_ID={topic_ids[0]}")
        print(f"HCS_TRADES_TOPIC_ID={topic_ids[1]}")

    print("\nDone (live mode).")


def main() -> None:
    if _SDK_AVAILABLE:
        run_live()
    else:
        run_stub()


if __name__ == "__main__":
    main()
