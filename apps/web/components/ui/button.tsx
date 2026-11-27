import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-navy text-white hover:opacity-90 dark:bg-accent dark:text-accentfg",
        accent: "bg-accent text-accentfg hover:opacity-90",
        outline: "border border-border bg-surface hover:bg-surface2",
        ghost: "hover:bg-surface2",
        danger: "bg-bad text-white hover:opacity-90 dark:text-black",
        success: "bg-ok text-white hover:opacity-90 dark:text-black",
        link: "text-accent underline-offset-2 hover:underline px-0",
      },
      size: { sm: "h-7 px-2.5", md: "h-8 px-3", lg: "h-10 px-4 text-sm", icon: "h-8 w-8" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, type = "button", ...p }, ref) => (
  <button ref={ref} type={type} className={cn(button({ variant, size }), className)} {...p} />
));
Button.displayName = "Button";
