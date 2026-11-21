import { useQueryClient } from "@tanstack/react-query";
import * as WebBrowser from "expo-web-browser";
import { useState } from "react";
import { Alert, Linking, Pressable, ScrollView, StyleSheet, Switch, View } from "react-native";

import { endpoints, type NoticeKind, type Notices } from "@/api/endpoints";
import { useMe, useNotices } from "@/api/hooks";
import { keys } from "@/api/query";
import { demo } from "@/api/reservas";
import { AUTOCLOSE_HOURS, type Autoclose } from "@/api/v13-ajustes";
import { useInboxAutoclose, type AutocloseState } from "@/api/v13-ajustes-hooks";
import { useSession } from "@/auth/session";
import { APP_VERSION, CONSOLE_URL, VARIANT } from "@/config";
import { versionLabel } from "@/lib/version";
import { groupsFor, kindsFor } from "@/features/notices";
import { useLocale, useT, type MessageKey, type T } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { DrawCheck } from "@/motion/micro";
import { usePush } from "@/push/provider";
import { glassAvailable } from "@/theme/glass";
import { TOUCH, useTheme } from "@/theme/theme";
import { Avatar, Divider, RowButton } from "@/ui/bits";
import { ChannelMark, type ChannelKind } from "@/ui/brand-icons";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Group } from "@/ui/group";
import { Icon, icons, type IconName } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { OfflineBanner } from "@/ui/states";
import { Text } from "@/ui/text";
import { switchColors } from "@/ui/switch-colors";

/** The published policy (Play's listing points at the same), in the person's language. */
const PRIVACY_URL = { es: "https://www.auphere.com/es/privacidad", en: "https://www.auphere.com/en/privacy" } as const;
const SUPPORT_EMAIL = "contacto@auphere.com";
/** The channels whose own mark the app draws (R1.3); any other kind is left out rather than drawn as one of these. */
const CHANNELS: readonly ChannelKind[] = ["whatsapp", "instagram", "messenger"];

/**
 * Ajustes (spec 031, R11; spec 042, R8; spec 044, R14; spec 069, R19, R17.2):
 *
 * - who you are here: the account, the business and the role;
 * - the connected channels, each with its mark and its state in words;
 * - this phone's notices by module (only the client's modules have a group,
 *   and a switch exists only when the system lets notices through, R10.3);
 *   turning the urgent one off asks first (R19.2); the quiet hours when the
 *   API has them;
 * - the Bandeja's inactivity close, only with the Bandeja (R17.2);
 * - the privacy policy, support and the web console — each a row that says it
 *   leaves the app and where to;
 * - signing out, which says that the agents keep answering and this phone
 *   stops getting notices (R19.3);
 * - and last, in its own group and the only one in the colour of danger,
 *   asking for the account's deletion, with what happens next; then the version.
 */
export default function Ajustes() {
  const t = useT();
  const locale = useLocale();
  const { colors } = useTheme();
  const online = useOnline();
  const me = useMe();
  const { signOut } = useSession();
  const push = usePush();
  const qc = useQueryClient();
  const granted = push.permission === "granted";
  const notices = useNotices(granted);
  const [saveFailed, setSaveFailed] = useState(false);
  const [deletion, setDeletion] = useState<"idle" | "sending" | "sent" | "failed">("idle");
  const modules = me.data?.nav ?? [];
  const agents = me.data?.agents ?? [];
  const autoclose = useInboxAutoclose(modules.includes("inbox"));
  const kinds = kindsFor(modules);
  const groups = groupsFor(modules);
  const on = new Set<NoticeKind>((notices.data?.kinds ?? []) as NoticeKind[]);
  const quiet = typeof notices.data?.quiet_outside_hours === "boolean" ? notices.data.quiet_outside_hours : null;

  /** One write of the whole set; with example Reservas (spec 044, D2) it stays in memory. */
  const save = async (nextKinds: NoticeKind[], nextQuiet: boolean | undefined) => {
    const before = notices.data;
    qc.setQueryData<Notices>(keys.notices, { ...before, kinds: nextKinds, ...(nextQuiet === undefined ? {} : { quiet_outside_hours: nextQuiet }) });
    setSaveFailed(false);
    try {
      const saved = demo
        ? await demo.setNotices({ kinds: nextKinds, ...(nextQuiet === undefined ? {} : { quiet_outside_hours: nextQuiet }) })
        : await endpoints.setNotices(nextKinds, nextQuiet);
      qc.setQueryData(keys.notices, saved);
    } catch {
      qc.setQueryData(keys.notices, before);
      setSaveFailed(true);
    }
  };

  const write = (kind: NoticeKind, value: boolean) =>
    void save(
      kinds.map((k) => k.kind).filter((k) => (k === kind ? value : on.has(k))),
      // The quiet hours travel along when the API has them, so a set never drops them.
      quiet ?? undefined,
    );

  const toggle = (kind: NoticeKind, value: boolean) => {
    haptics.select();
    // R19.2: the urgent notice asks before going off; switching it back on does not.
    if (kind === "inbox.waiting" && !value) {
      Alert.alert(t("v13.settings.urgent.title"), t("v13.settings.urgent.body"), [
        { text: t("v13.settings.urgent.keep"), style: "cancel" },
        { text: t("v13.settings.urgent.off"), onPress: () => write(kind, false) },
      ]);
      return;
    }
    write(kind, value);
  };

  const confirmSignOut = () => {
    const only = agents.length === 1 ? agents[0] : undefined;
    const body = only
      ? t("v13.settings.signOut.body.agent", { agent: only.name })
      : agents.length > 1
        ? t("v13.settings.signOut.body.agents")
        : t("v13.settings.signOut.body");
    Alert.alert(t("v13.settings.signOut.title"), body, [
      { text: t("app.cancel"), style: "cancel" },
      {
        text: t("app.signOut"),
        onPress: () => {
          haptics.light();
          void signOut();
        },
      },
    ]);
  };

  const confirmDeletion = () =>
    Alert.alert(t("app.deletion.confirm"), t("app.deletion.body"), [
      { text: t("app.cancel"), style: "cancel" },
      {
        text: t("app.deletion"),
        style: "destructive",
        onPress: () => {
          setDeletion("sending");
          void endpoints
            .requestDeletion()
            .then(() => setDeletion("sent"))
            .catch(() => setDeletion("failed"));
        },
      },
    ]);

  const name = me.data?.user.name ?? "";

  return (
    // With Liquid Glass the sheet's own material shows through; before it, the container is opaque (spec 042, R1.7).
    <ScrollView
      testID="settings-scroll"
      style={glassAvailable() ? undefined : { backgroundColor: colors.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
    >
      {!online ? <OfflineBanner /> : null}

      <Card testID="settings-account">
        <View style={styles.account}>
          <Avatar initials={initialsOf(name)} size={52} />
          <View style={styles.flex}>
            <Text variant="name">{name}</Text>
            <Text variant="callout" tone="mutedForeground" selectable>
              {me.data?.user.email ?? ""}
            </Text>
          </View>
        </View>
        <Divider />
        <Line icon={icons.store} label={t("app.account.business")} value={me.data?.client.name ?? ""} />
        <Line icon={icons.badge} label={t("app.account.role")} value={t("app.account.role.client")} />
      </Card>

      <Channels channels={me.data?.channels ?? []} agents={agents} t={t} />

      <Card testID="settings-notices">
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("app.notices.section")}
        </Text>
        {granted && !notices.data && notices.isError ? (
          // Never switches drawn off without the data (review H02, R3.1): what happened, and again.
          <View style={styles.group}>
            <Text variant="callout" tone="mutedForeground" accessibilityRole="alert">
              {t("v13.settings.notices.error")}
            </Text>
            <Button label={t("app.retry")} icon={icons.retry} variant="secondary" compact onPress={() => void notices.refetch()} />
          </View>
        ) : granted && !notices.data ? (
          <View style={styles.group} accessible accessibilityRole="progressbar" accessibilityLabel={t("v13.settings.notices.loading")} accessibilityState={{ busy: true }}>
            <Text variant="callout" tone="mutedForeground">
              {t("v13.settings.notices.loading")}
            </Text>
          </View>
        ) : granted ? (
          <>
            {groups.map((g) => (
              <View key={g.group} style={styles.group}>
                <Text variant="footnote" tone="mutedForeground" accessibilityRole="header">
                  {t(g.label)}
                </Text>
                {g.kinds.map((k, i) => (
                  <View key={k.kind}>
                    {i > 0 ? <Divider /> : null}
                    <SwitchRow
                      icon={k.icon}
                      label={t(k.label)}
                      hint={t(k.hint)}
                      value={on.has(k.kind)}
                      disabled={!online || !notices.data}
                      onChange={(v) => toggle(k.kind, v)}
                    />
                  </View>
                ))}
              </View>
            ))}
            {quiet !== null ? (
              <View style={styles.group}>
                <Divider />
                <SwitchRow
                  icon={icons.bellOff}
                  label={t("avisos.quiet")}
                  hint={me.data?.business?.hours_label ? t("avisos.quiet.hint", { hours: me.data.business.hours_label }) : t("avisos.quiet.hint.noHours")}
                  value={quiet}
                  disabled={!online || !notices.data}
                  onChange={(v) => {
                    haptics.select();
                    void save([...on].filter((k) => kinds.some((x) => x.kind === k)), v);
                  }}
                />
              </View>
            ) : null}
          </>
        ) : push.permission === "denied" ? (
          <>
            <Text variant="callout">{t("app.notices.denied")}</Text>
            <Button label={t("app.notices.denied.open")} variant="secondary" onPress={() => void Linking.openSettings()} />
          </>
        ) : (
          <>
            <Text variant="callout">{t("app.notices.off")}</Text>
            <Button label={t("app.notices.allow")} onPress={() => void push.enable()} />
          </>
        )}
        {saveFailed ? (
          <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
            {t("app.notices.saveFailed")}
          </Text>
        ) : null}
        <Text variant="footnote" tone="mutedForeground">
          {t("app.notices.privacy")}
        </Text>
      </Card>

      {autoclose.state !== "off" ? <InboxClose autoclose={autoclose} online={online} t={t} /> : null}

      <Group testID="settings-help" title={t("v13.settings.help")}>
        <RowButton
          icon={icons.privacy}
          title={t("v13.settings.privacy")}
          subtitle={new URL(PRIVACY_URL[locale]).host}
          kind="external"
          onPress={() => void WebBrowser.openBrowserAsync(PRIVACY_URL[locale])}
        />
        <RowButton
          icon={icons.support}
          title={t("v13.settings.support")}
          subtitle={SUPPORT_EMAIL}
          kind="external"
          accessibilityHint={t("v13.settings.support.hint")}
          // A phone with no mail app refuses; the address is on screen to copy by hand.
          onPress={() => void Linking.openURL(`mailto:${SUPPORT_EMAIL}`).catch(() => undefined)}
        />
      </Group>

      <Group testID="settings-web">
        <RowButton
          icon={icons.globe}
          title={t("app.web")}
          subtitle={new URL(CONSOLE_URL).host}
          kind="external"
          tone="primaryText"
          onPress={() => void WebBrowser.openBrowserAsync(CONSOLE_URL)}
        />
      </Group>

      <Group testID="settings-signout" title={t("v13.settings.session")}>
        <RowButton icon={icons.logOut} title={t("avisos.signOut.row")} kind="action" onPress={confirmSignOut} />
      </Group>

      <View style={styles.last}>
        <Group testID="settings-deletion">
          <RowButton
            icon={icons.trash}
            title={t("app.deletion")}
            tone="destructive"
            kind="action"
            onPress={confirmDeletion}
            accessibilityHint={t("app.deletion.body")}
          />
          {deletion !== "idle" ? (
            <Text
              variant="footnote"
              tone={deletion === "failed" ? "dangerText" : "mutedForeground"}
              accessibilityRole="alert"
              style={styles.status}
            >
              {deletion === "sending" ? t("app.loading") : deletion === "sent" ? t("app.deletion.sent") : t("app.deletion.failed")}
            </Text>
          ) : null}
        </Group>
        <Text variant="footnote" tone="mutedForeground" style={styles.footer}>
          {t("app.deletion.footer")}
        </Text>
      </View>

      <Text variant="caption" tone="mutedForeground" style={styles.version}>
        {t("v13.settings.version", { version: versionLabel(APP_VERSION, VARIANT) })}
      </Text>
    </ScrollView>
  );
}

/**
 * The connected channels (R19.1): `/me.channels` by kind, each with its own
 * mark and its state in words — «Conectado», «Sin conectar» or «1 de 2
 * conectados». The API gives no number or handle, so none is invented.
 */
function Channels({ channels, agents, t }: { channels: readonly { kind: string; connected: boolean }[]; agents: readonly { name: string }[]; t: T }) {
  const rows = CHANNELS.map((kind) => {
    const of = channels.filter((c) => c.kind === kind);
    return { kind, total: of.length, connected: of.filter((c) => c.connected).length };
  }).filter((r) => r.total > 0);
  // Only kinds the app does not draw: saying «none» would not be true either.
  if (rows.length === 0 && channels.length > 0) return null;
  const all = rows.length > 0 && rows.every((r) => r.connected === r.total);
  const only = agents.length === 1 ? agents[0] : undefined;
  return (
    <View testID="settings-channels" style={styles.section}>
      <View style={styles.sectionHead}>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("v13.settings.channels")}
        </Text>
        {all && only ? (
          <Text variant="footnote" tone="mutedForeground">
            {t("v13.settings.channels.agent", { agent: only.name })}
          </Text>
        ) : null}
      </View>
      {rows.length === 0 ? (
        <Card>
          <Text variant="callout" tone="mutedForeground">
            {t("v13.settings.channels.none")}
          </Text>
        </Card>
      ) : (
        <Group>
          {rows.map((r) => {
            const state =
              r.connected === r.total
                ? t("v13.settings.channel.on")
                : r.connected === 0
                  ? t("v13.settings.channel.off")
                  : t("v13.settings.channel.some", { n: r.connected, total: r.total });
            return <ChannelRow key={r.kind} kind={r.kind} name={t(`v13.settings.channel.${r.kind}` as MessageKey)} state={state} on={r.connected > 0} />;
          })}
        </Group>
      )}
    </View>
  );
}

function ChannelRow({ kind, name, state, on }: { kind: ChannelKind; name: string; state: string; on: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={styles.channel} accessible accessibilityLabel={`${name}: ${state}`} testID={`settings-channel-${kind}`}>
      <ChannelMark kind={kind} size={18} />
      <Text variant="body" style={styles.flex}>
        {name}
      </Text>
      <View style={styles.state}>
        {/* The state is said in words; the dot only repeats it (never colour alone, WCAG 1.4.1). */}
        <View style={[styles.stateDot, { backgroundColor: on ? colors.positive : colors.subtle }]} />
        <Text variant="callout" tone={on ? "positiveText" : "mutedForeground"}>
          {state}
        </Text>
      </View>
    </View>
  );
}

const AUTOCLOSE_LABEL: Record<NonNullable<Autoclose>, MessageKey> = {
  24: "inbox.settings.autoclose.24",
  72: "inbox.settings.autoclose.72",
  168: "inbox.settings.autoclose.168",
  720: "inbox.settings.autoclose.720",
};

/**
 * The Bandeja's inactivity close (R17.2; spec 064, R5): the web's own five
 * choices as one radio group, the stored one ticked with the check that draws
 * itself (micro 2). Offline nothing can be chosen.
 */
function InboxClose({ autoclose, online, t }: { autoclose: Exclude<AutocloseState, { state: "off" }>; online: boolean; t: T }) {
  const choices: Autoclose[] = [null, ...AUTOCLOSE_HOURS];
  return (
    <Group testID="settings-inbox" title={t("avisos.group.inbox")}>
      <View style={styles.inboxHead}>
        <Text variant="body">{t("inbox.settings.autoclose")}</Text>
        <Text variant="footnote" tone="mutedForeground">
          {t("inbox.settings.autoclose.hint")}
        </Text>
      </View>
      {autoclose.state === "loading" ? (
        <View style={styles.inboxBody} accessible accessibilityRole="progressbar" accessibilityLabel={t("inbox.settings.loading")} accessibilityState={{ busy: true }}>
          <Text variant="callout" tone="mutedForeground">
            {t("inbox.settings.loading")}
          </Text>
        </View>
      ) : autoclose.state === "error" ? (
        <View style={styles.inboxBody}>
          <Text variant="callout" tone="mutedForeground" accessibilityRole="alert">
            {t("inbox.settings.error")}
          </Text>
          <Button label={t("app.retry")} icon={icons.retry} variant="secondary" compact onPress={autoclose.retry} />
        </View>
      ) : (
        <View accessibilityRole="radiogroup" accessibilityLabel={t("inbox.settings.autoclose")}>
          {choices.map((h, i) => (
            <View key={String(h)}>
              {i > 0 ? <Divider /> : null}
              <Choice
                label={h === null ? t("inbox.settings.autoclose.never") : t(AUTOCLOSE_LABEL[h])}
                checked={autoclose.hours === h}
                disabled={!online || autoclose.status === "saving"}
                onPress={() => {
                  haptics.select();
                  void autoclose.save(h);
                }}
              />
            </View>
          ))}
          {autoclose.status === "failed" || autoclose.status === "saved" ? (
            <Text
              variant="footnote"
              tone={autoclose.status === "failed" ? "dangerText" : "mutedForeground"}
              accessibilityRole="alert"
              accessibilityLiveRegion="polite"
              style={styles.inboxStatus}
            >
              {autoclose.status === "failed" ? t("inbox.settings.saveError") : t("inbox.settings.saved")}
            </Text>
          ) : null}
        </View>
      )}
    </Group>
  );
}

function Choice({ label, checked, disabled, onPress }: { label: string; checked: boolean; disabled: boolean; onPress: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityLabel={label}
      accessibilityState={{ checked, disabled }}
      disabled={disabled}
      onPress={onPress}
      android_ripple={{ color: colors.muted }}
      style={({ pressed }) => [styles.choice, pressed ? { backgroundColor: colors.muted } : null]}
    >
      <Text variant="body" tone={disabled && !checked ? "mutedForeground" : "foreground"} style={styles.flex}>
        {label}
      </Text>
      {/* The chosen one says it with the check, never with colour alone. */}
      {checked ? <DrawCheck size={20} color={colors.primaryText} /> : null}
    </Pressable>
  );
}

/** A notice switch with its icon and hint, named for the screen reader by its label. */
function SwitchRow({
  icon,
  label,
  hint,
  value,
  disabled,
  onChange,
}: {
  icon: IconName;
  label: string;
  hint: string;
  value: boolean;
  disabled: boolean;
  onChange: (v: boolean) => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.switchRow}>
      <Icon name={icon} size={20} tone="mutedForeground" />
      <View style={styles.flex}>
        <Text variant="body">{label}</Text>
        <Text variant="footnote" tone="mutedForeground">
          {hint}
        </Text>
      </View>
      <Switch accessibilityLabel={label} value={value} disabled={disabled} onValueChange={onChange} {...switchColors(colors)} />
    </View>
  );
}

function Line({ icon, label, value }: { icon: IconName; label: string; value: string }) {
  return (
    <View style={styles.line} accessible accessibilityLabel={`${label}: ${value}`}>
      <Icon name={icon} size={18} tone="mutedForeground" />
      <Text variant="callout" tone="mutedForeground" style={styles.flex}>
        {label}
      </Text>
      <Text variant="callout" style={styles.value}>
        {value}
      </Text>
    </View>
  );
}

/** «VR» for Valeria Ríos: the first letters of the first two words. */
function initialsOf(name: string): string {
  const parts = name.split(/\s+/).filter((p) => /^\p{L}/u.test(p));
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "·";
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 16, paddingBottom: 40 },
  account: { flexDirection: "row", alignItems: "center", gap: 14 },
  section: { gap: 8 },
  sectionHead: { paddingHorizontal: 4, gap: 2 },
  switchRow: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingVertical: 8 },
  group: { gap: 2, paddingTop: 4 },
  flex: { flex: 1, minWidth: 0, gap: 2 },
  line: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: TOUCH, flexWrap: "wrap" },
  channel: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingHorizontal: 16, paddingVertical: 10, flexWrap: "wrap" },
  value: { flexShrink: 1, textAlign: "right" },
  state: { flexDirection: "row", alignItems: "center", gap: 6 },
  stateDot: { width: 8, height: 8, borderRadius: 4 },
  inboxHead: { paddingHorizontal: 16, paddingVertical: 12, gap: 4 },
  inboxBody: { paddingHorizontal: 16, paddingVertical: 12, gap: 10, alignItems: "flex-start" },
  inboxStatus: { paddingHorizontal: 16, paddingVertical: 10 },
  choice: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingHorizontal: 16, paddingVertical: 10 },
  // Signing out is everyday; deleting the account is rare and final. Distance between them (R8.1).
  last: { gap: 8, marginTop: 8 },
  status: { paddingHorizontal: 16, paddingVertical: 12 },
  footer: { paddingHorizontal: 4 },
  version: { textAlign: "center" },
});
