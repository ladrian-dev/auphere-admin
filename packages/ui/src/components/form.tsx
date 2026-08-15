"use client";

/**
 * Minimal react-hook-form bridge in the shadcn/ui style. The 4.x shadcn
 * registry no longer ships this file by default (it favours Base UI's
 * own form primitives), but the API is stable and our pages use it.
 *
 * Adapted from the v3 shadcn `form.tsx` reference, trimmed to the parts
 * we use: Form, FormField, FormItem, FormLabel, FormControl, FormMessage,
 * FormDescription. ``FormControl`` clones its single child with the aria
 * wiring (Base UI ``mergeProps`` — no Radix in this package).
 */

import * as React from "react";
import { mergeProps } from "@base-ui/react/merge-props";
import {
  Controller,
  FormProvider,
  useFormContext,
  useFormState,
  type ControllerProps,
  type FieldPath,
  type FieldValues,
} from "react-hook-form";

import { cn } from "../lib/utils";
import { Label } from "./label";

const Form = FormProvider;

type FormFieldContextValue<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
> = { name: TName };

const FormFieldContext = React.createContext<FormFieldContextValue | null>(null);

function FormField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>({ ...props }: ControllerProps<TFieldValues, TName>) {
  return (
    <FormFieldContext.Provider value={{ name: props.name }}>
      <Controller {...props} />
    </FormFieldContext.Provider>
  );
}

const FormItemContext = React.createContext<{ id: string } | null>(null);

function useFormField() {
  const fieldContext = React.useContext(FormFieldContext);
  const itemContext = React.useContext(FormItemContext);
  const { getFieldState } = useFormContext();
  const formState = useFormState({ name: fieldContext?.name });
  if (!fieldContext) {
    throw new Error("useFormField must be used inside <FormField>");
  }
  const fieldState = getFieldState(fieldContext.name, formState);
  const id = itemContext?.id ?? "form-field";
  return {
    id,
    name: fieldContext.name,
    formItemId: `${id}-form-item`,
    formDescriptionId: `${id}-form-item-description`,
    formMessageId: `${id}-form-item-message`,
    ...fieldState,
  };
}

function FormItem({ className, ...props }: React.ComponentProps<"div">) {
  const id = React.useId();
  return (
    <FormItemContext.Provider value={{ id }}>
      <div
        data-slot="form-item"
        className={cn("grid gap-2", className)}
        {...props}
      />
    </FormItemContext.Provider>
  );
}

function FormLabel({
  className,
  ...props
}: React.ComponentProps<typeof Label>) {
  const { error, formItemId } = useFormField();
  return (
    <Label
      data-slot="form-label"
      data-error={!!error}
      className={cn("data-[error=true]:text-destructive", className)}
      htmlFor={formItemId}
      {...props}
    />
  );
}

type FormControlProps = React.HTMLAttributes<HTMLElement> & {
  children: React.ReactElement<Record<string, unknown>>;
};

function FormControl({ children, ...props }: FormControlProps) {
  const { error, formItemId, formDescriptionId, formMessageId } = useFormField();
  const controlProps = {
    "data-slot": "form-control",
    id: formItemId,
    "aria-describedby": !error ? `${formDescriptionId}` : `${formDescriptionId} ${formMessageId}`,
    "aria-invalid": !!error,
  };
  return React.cloneElement(
    children,
    mergeProps(controlProps, props as Record<string, unknown>, children.props),
  );
}

function FormDescription({
  className,
  ...props
}: React.ComponentProps<"p">) {
  const { formDescriptionId } = useFormField();
  return (
    <p
      data-slot="form-description"
      id={formDescriptionId}
      className={cn("text-muted-foreground text-xs leading-snug", className)}
      {...props}
    />
  );
}

/**
 * Always-rendered slot. Even when there is no error, the `<p>` reserves a
 * fixed-height line so the next row in a grid doesn't jump 16px when
 * validation kicks in. The aria-live region keeps screen readers in sync.
 */
function FormMessage({
  className,
  children,
  ...props
}: React.ComponentProps<"p">) {
  const { error, formMessageId } = useFormField();
  const body = error ? String(error?.message ?? "") : children;
  return (
    <p
      data-slot="form-message"
      id={formMessageId}
      aria-live="polite"
      className={cn(
        "min-h-4 text-destructive text-xs leading-snug",
        className,
      )}
      {...props}
    >
      {body ?? " "}
    </p>
  );
}

export {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  useFormField,
};
