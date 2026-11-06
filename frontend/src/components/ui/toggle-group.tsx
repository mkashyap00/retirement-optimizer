"use client";

import * as React from "react";
import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import { cn } from "@/lib/utils";

const ToggleGroupContext = React.createContext<{ size?: "sm" | "default" }>({});

const ToggleGroup = React.forwardRef<
  React.ElementRef<typeof ToggleGroupPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ToggleGroupPrimitive.Root> & {
    size?: "sm" | "default";
  }
>(({ className, size = "default", children, ...props }, ref) => (
  <ToggleGroupContext.Provider value={{ size }}>
    <ToggleGroupPrimitive.Root
      ref={ref}
      className={cn(
        "inline-flex rounded-md border border-border bg-muted/40 p-0.5 gap-0.5",
        className
      )}
      {...props}
    >
      {children}
    </ToggleGroupPrimitive.Root>
  </ToggleGroupContext.Provider>
));
ToggleGroup.displayName = ToggleGroupPrimitive.Root.displayName;

const ToggleGroupItem = React.forwardRef<
  React.ElementRef<typeof ToggleGroupPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof ToggleGroupPrimitive.Item>
>(({ className, children, ...props }, ref) => {
  const { size } = React.useContext(ToggleGroupContext);
  return (
    <ToggleGroupPrimitive.Item
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-sm font-medium transition-all",
        "text-muted-foreground ring-offset-background",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
        "disabled:pointer-events-none disabled:opacity-50",
        // Active state: accent (gold) background with foreground text
        "data-[state=on]:bg-accent data-[state=on]:text-accent-foreground data-[state=on]:shadow-sm",
        "hover:bg-muted hover:text-foreground",
        size === "sm" ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm",
        className
      )}
      {...props}
    >
      {children}
    </ToggleGroupPrimitive.Item>
  );
});
ToggleGroupItem.displayName = ToggleGroupPrimitive.Item.displayName;

export { ToggleGroup, ToggleGroupItem };
