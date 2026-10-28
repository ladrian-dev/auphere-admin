import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";

import { cn } from "../lib/utils";

/**
 * The one Button (PLAN-CONSOLE-V1 §5). Every control that sits next to a
 * Button (Input, SelectTrigger) shares its geometry:
 *
 *   xs 24 px · sm 32 px · default 36 px · lg 40 px   (heights)
 *   px-2 / px-3 / px-4 / px-5                        (horizontal padding)
 *   icon 16 px (size-4), 12 px in xs                  (icons)
 *
 * All on the 4 px grid; radius is ``rounded-md`` (8 px). Spec 047: the
 * geometry of the approved prototype «Consola de partners v2» (36/30 px and
 * 8 px; 30 rounds up to the grid). There are no other sizes — if a design needs one, it is a design
 * change, not a className.
 *
 * ``no-underline`` en la base: un Button que se pinta como enlace
 * (``render={<Link/>}``) es un ``<a href>``, y eso lo expone a todo lo que
 * en esta base de código subraya anclas. La variante ``link`` lo recupera en
 * hover, que es donde sí lo quiere.
 *
 * No basta con esto, y conviene saberlo: ``Callout`` y ``Alert`` subrayaban
 * **toda** ancla que contuvieran (``[&_a]:underline``), y ese selector gana
 * en especificidad. Salía en tres botones «Conectar» de la tarjeta de
 * conectores que estorban (owner, 2026-09-28). Ahora esos dos excluyen
 * ``[data-slot=button]``: un aviso subraya los enlaces de su texto, no los
 * botones que lleva dentro.
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 cursor-pointer items-center justify-center whitespace-nowrap rounded-md border border-transparent bg-clip-padding text-sm font-medium no-underline transition-[background-color,color,border-color,box-shadow,transform] duration-(--duration-fast) select-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/85 [a]:hover:bg-primary/85",
        outline:
          "border-border bg-background hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground",
        destructive:
          "bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20",
        link: "text-primary-text underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-9 gap-2 px-4 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        xs: "h-6 gap-1 px-2 text-xs has-data-[icon=inline-end]:pr-1 has-data-[icon=inline-start]:pl-1 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-2 px-3 text-sm has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        lg: "h-10 gap-2 px-5 text-base has-data-[icon=inline-end]:pr-4 has-data-[icon=inline-start]:pl-4",
        icon: "size-9",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

type ButtonProps = ButtonPrimitive.Props &
  VariantProps<typeof buttonVariants> & {
    /** Bloque C: busy and disabled, with a spinner in the icon slot and the
     *  label kept in place so the button does not change width. */
    loading?: boolean;
  };

function Button({ className, variant = "default", size = "default", loading, disabled, children, ...props }: ButtonProps) {
  return (
    <ButtonPrimitive
      data-slot="button"
      data-loading={loading || undefined}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    >
      {loading ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
      {children}
    </ButtonPrimitive>
  );
}

export { Button, buttonVariants, type ButtonProps };
