import * as React from "react"
import { cn } from "@/lib/utils"

function Badge({
  className,
  ...props
}: React.ComponentProps<"span">) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-[#1a1a1a] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        className
      )}
      {...props}
    />
  )
}

export { Badge }
