import { Field, Input, NativeSelect } from "@nexus/ui";

import { credentialFieldHint, credentialFieldLabel, credentialOptionLabel, credentialValue } from "@/components/agent-tools/lib";
import { useT } from "@/i18n/client";
import { messages, type MessageKey } from "@/i18n/messages";
import type { CredentialsField } from "@/lib/backend/agent-tools-types";

/**
 * Un campo del formulario de conexión por clave, igual en la tarjeta de Conectores y
 * en la página de la conexión (spec 061, 1.7).
 *
 * Con `options` es un desplegable, y su primera opción vale de entrada: lo que se
 * envía es lo que se ve (`credentialValue`). Si no, es texto, o clave si es secreto.
 * La etiqueta se queda en una línea (`Field` la recorta), así que lo que explica de
 * dónde sale el dato va como ayuda debajo. El entorno de Quédate era un texto libre
 * con toda la explicación en la etiqueta, y se cortaba.
 */
export function CredentialField({
  slug,
  field,
  id,
  values,
  onChange,
  error,
  disabled,
}: {
  slug: string;
  field: CredentialsField;
  id: string;
  values: Record<string, string>;
  onChange: (value: string) => void;
  error?: string;
  disabled?: boolean;
}) {
  const t = useT();
  const translate = (key: string) => t(key as MessageKey);
  return (
    <Field
      label={credentialFieldLabel(slug, field, messages, translate)}
      hint={credentialFieldHint(slug, field, messages, translate)}
      htmlFor={id}
      required={field.required !== false}
      error={error}
    >
      {(a11y) =>
        field.options?.length ? (
          <NativeSelect
            {...a11y}
            wrapperClassName="w-full"
            value={credentialValue(field, values)}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
          >
            {field.options.map((option) => (
              <option key={option.value} value={option.value}>
                {credentialOptionLabel(slug, field, option, messages, translate)}
              </option>
            ))}
          </NativeSelect>
        ) : (
          <Input
            {...a11y}
            type={field.secret ? "password" : "text"}
            autoComplete={field.secret ? "new-password" : "off"}
            spellCheck={false}
            placeholder={field.placeholder}
            value={values[field.field] ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
          />
        )
      }
    </Field>
  );
}
