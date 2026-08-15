import { redirect } from "next/navigation";

import { getT } from "@/i18n/server";
import { getSession } from "@/lib/session";

import { LoginForm } from "./login-form";

export const metadata = { title: "Login" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ from?: string }> }) {
  const session = await getSession();
  if (session) redirect("/");
  const { from } = await searchParams;
  const { t } = await getT();
  const redirectTo = from && from.startsWith("/") && !from.startsWith("//") ? from : "/";
  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-3xl font-semibold">{t("login.title")}</h1>
      <LoginForm redirectTo={redirectTo} />
    </section>
  );
}
