<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">
          {{ __("SLA Monitor") }}
        </div>
      </template>
      <template #right-header>
        <div class="flex items-center gap-3">
          <span v-if="lastUpdated" class="text-sm text-ink-gray-5">
            {{ __("Updated {0}", [lastUpdated]) }}
          </span>
          <Button
            :label="__('Refresh')"
            variant="subtle"
            icon-left="lucide-refresh-ccw"
            :loading="monitor.loading"
            @click="monitor.reload()"
          />
        </div>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto px-3 py-4 sm:px-5">
      <!-- Escalation warning -->
      <div
        v-if="summary.needs_escalation > 0"
        class="mb-4 flex items-start gap-3 rounded-4 border border-outline-red-2 bg-surface-red-1 p-3"
        data-testid="sla-escalation-banner"
      >
        <LucideTriangleAlert class="mt-0.5 size-4 shrink-0 text-ink-red-6" />
        <div class="text-base text-ink-gray-8">
          <span class="font-semibold text-ink-red-6">
            {{
              __("{0} ticket(s) need escalation", [summary.needs_escalation])
            }}
          </span>
          <span class="text-ink-gray-7">
            &middot;
            {{
              __("{0} overdue, {1} past the {2}% warning threshold", [
                summary[OVERDUE],
                summary[AT_RISK],
                settings.warning_threshold,
              ])
            }}
          </span>
        </div>
      </div>

      <!-- Summary tiles, also act as state filters -->
      <div class="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <button
          v-for="tile in tiles"
          :key="tile.value"
          type="button"
          class="flex flex-col gap-1 rounded-4 border p-3 text-start transition-colors"
          :class="
            stateFilter === tile.value
              ? 'border-outline-gray-4 bg-surface-gray-2'
              : 'border-outline-gray-2 hover:bg-surface-gray-1'
          "
          @click="stateFilter = tile.value"
        >
          <span class="flex items-center gap-1.5 text-sm text-ink-gray-6">
            <span
              v-if="tile.value"
              class="size-2 rounded-full"
              :class="STATE_STYLE[tile.value].dot"
            />
            {{ tile.label }}
          </span>
          <span class="text-2xl font-semibold text-ink-gray-9">
            {{ tile.count }}
          </span>
        </button>
      </div>

      <!-- Filters -->
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <TextInput
          v-model="filters.search"
          class="w-full sm:w-64"
          type="text"
          :placeholder="__('Search ID, subject or email')"
          :debounce="400"
        >
          <template #prefix>
            <LucideSearch class="size-4 text-ink-gray-5" />
          </template>
        </TextInput>
        <Link
          v-model="filters.team"
          class="w-full sm:w-48"
          doctype="HD Team"
          variant="outline"
          :placeholder="__('Team')"
        />
        <Select
          v-model="filters.priority"
          class="w-full sm:w-40"
          :options="priorityOptions"
          :placeholder="__('Priority')"
        />
        <Checkbox
          v-model="filters.assigned_to_me"
          size="sm"
          :label="__('Assigned to me')"
        />
      </div>

      <!-- Ticket table -->
      <div class="overflow-x-auto rounded-4 border border-outline-gray-2">
        <table class="w-full table-auto text-base">
          <thead class="bg-surface-gray-2 text-sm text-ink-gray-6">
            <tr>
              <th
                v-for="column in COLUMNS"
                :key="column.key"
                class="whitespace-nowrap px-3 py-2 text-start font-normal"
                :class="column.class"
              >
                {{ column.label }}
              </th>
            </tr>
          </thead>
          <tbody v-if="visibleTickets.length">
            <tr
              v-for="ticket in visibleTickets"
              :key="ticket.name"
              class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1"
              @click="openTicket(ticket.name)"
            >
              <td class="whitespace-nowrap px-3 py-2.5 text-ink-gray-6">
                #{{ ticket.name }}
              </td>
              <td class="max-w-0 px-3 py-2.5">
                <div class="truncate text-ink-gray-8">{{ ticket.subject }}</div>
                <div
                  v-if="ticket.escalation_warning"
                  class="mt-0.5 flex items-center gap-1 truncate text-sm"
                  :class="STATE_STYLE[ticket.liveState].text"
                >
                  <LucideTriangleAlert class="size-3 shrink-0" />
                  <span class="truncate">{{ ticket.escalation_warning }}</span>
                </div>
              </td>
              <td class="whitespace-nowrap px-3 py-2.5">
                <TicketPriority :priority="ticket.priority" />
              </td>
              <td class="whitespace-nowrap px-3 py-2.5 text-ink-gray-7">
                {{ ticket.agent_group || __("No team") }}
              </td>
              <td class="whitespace-nowrap px-3 py-2.5 text-ink-gray-7">
                {{ __(ticket.stage) }}
              </td>
              <td class="whitespace-nowrap px-3 py-2.5 text-ink-gray-7">
                <Tooltip :text="dayjsLocal(ticket.due).format('LLLL')">
                  <span>{{
                    dayjsLocal(ticket.due).format("MMM D, h:mm A")
                  }}</span>
                </Tooltip>
              </td>
              <td
                class="whitespace-nowrap px-3 py-2.5 font-medium tabular-nums"
                :class="STATE_STYLE[ticket.liveState].text"
              >
                {{ remainingLabel(ticket) }}
              </td>
              <td class="px-3 py-2.5">
                <div class="flex items-center gap-2">
                  <div
                    class="h-1.5 w-24 overflow-hidden rounded-full bg-surface-gray-3"
                  >
                    <div
                      class="h-full rounded-full"
                      :class="STATE_STYLE[ticket.liveState].bar"
                      :style="{ width: `${ticket.liveUsed}%` }"
                    />
                  </div>
                  <span class="text-sm tabular-nums text-ink-gray-6">
                    {{ Math.round(ticket.liveUsed) }}%
                  </span>
                </div>
              </td>
              <td class="whitespace-nowrap px-3 py-2.5">
                <Badge
                  :label="__(ticket.liveState)"
                  :theme="STATE_STYLE[ticket.liveState].theme"
                  variant="subtle"
                />
              </td>
            </tr>
          </tbody>
        </table>
        <div
          v-if="!visibleTickets.length"
          class="flex flex-col items-center gap-2 py-16 text-center"
        >
          <LoadingIndicator v-if="monitor.loading" class="size-6" />
          <template v-else>
            <LucideShieldCheck class="size-8 text-ink-gray-4" />
            <span class="text-base text-ink-gray-7">
              {{ __("No open tickets with an SLA match these filters") }}
            </span>
          </template>
        </div>
      </div>
      <div v-if="visibleTickets.length" class="mt-2 text-sm text-ink-gray-5">
        {{ __("Showing {0} ticket(s)", [visibleTickets.length]) }}
        <template v-if="settings.refresh_interval">
          &middot;
          {{ __("auto refresh every {0}s", [settings.refresh_interval]) }}
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * SLA Monitor: every open ticket with an SLA, ordered by urgency, with the
 * time left on its current target (first response or resolution), how much
 * of the SLA window is used, and an escalation warning once the threshold
 * from HD Settings is crossed. Data comes from helpdesk.api.sla_monitor.
 */
import { LayoutHeader } from "@/components";
import TicketPriority from "@/components/TicketPriority.vue";
import { useTicketPriorityStore } from "@/stores/ticketPriority";
import { __ } from "@/translation";
import { Link } from "@framework/ui";
import {
  Badge,
  Button,
  Checkbox,
  createResource,
  dayjsLocal,
  LoadingIndicator,
  Select,
  TextInput,
  Tooltip,
  usePageMeta,
} from "frappe-ui";
import { useIntervalFn, useNow } from "@vueuse/core";
import { computed, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";

type State = "Overdue" | "At Risk" | "On Track" | "Paused";

interface MonitorTicket {
  name: string;
  subject: string;
  priority: string;
  agent_group: string | null;
  stage: string;
  due: string;
  remaining_seconds: number;
  used_percent: number;
  state: State;
  escalation_warning: string | null;
}

const OVERDUE: State = "Overdue";
const AT_RISK: State = "At Risk";
const ON_TRACK: State = "On Track";
const PAUSED: State = "Paused";

// One place for the colour of each state: dot, text, bar and badge theme.
const STATE_STYLE: Record<
  State,
  { dot: string; text: string; bar: string; theme: string }
> = {
  [OVERDUE]: {
    dot: "bg-surface-red-6",
    text: "text-ink-red-6",
    bar: "bg-surface-red-6",
    theme: "red",
  },
  [AT_RISK]: {
    dot: "bg-surface-orange-6",
    text: "text-ink-orange-6",
    bar: "bg-surface-orange-6",
    theme: "orange",
  },
  [ON_TRACK]: {
    dot: "bg-surface-green-6",
    text: "text-ink-green-6",
    bar: "bg-surface-green-6",
    theme: "green",
  },
  [PAUSED]: {
    dot: "bg-surface-blue-6",
    text: "text-ink-blue-6",
    bar: "bg-surface-blue-6",
    theme: "blue",
  },
};

const COLUMNS = [
  { key: "name", label: __("ID") },
  { key: "subject", label: __("Subject"), class: "w-full" },
  { key: "priority", label: __("Priority") },
  { key: "team", label: __("Team") },
  { key: "stage", label: __("SLA stage") },
  { key: "due", label: __("Due") },
  { key: "remaining", label: __("Time left") },
  { key: "used", label: __("SLA used") },
  { key: "state", label: __("State") },
];

const router = useRouter();
const { priorities } = useTicketPriorityStore();

const stateFilter = ref<State | "">("");
const filters = reactive({
  search: "",
  team: "",
  priority: "",
  assigned_to_me: false,
});

const monitor = createResource({
  url: "helpdesk.api.sla_monitor.get_sla_monitor",
  makeParams: () => ({ ...filters }),
  auto: true,
  onSuccess: () => {
    fetchedAt.value = Date.now();
  },
});

// filters other than the state tiles are applied on the server
watch(filters, () => monitor.reload(), { deep: true });

const settings = computed(
  () => monitor.data?.settings || { warning_threshold: 0, refresh_interval: 0 }
);

const summary = computed(
  () =>
    monitor.data?.summary || {
      total: 0,
      needs_escalation: 0,
      [OVERDUE]: 0,
      [AT_RISK]: 0,
      [ON_TRACK]: 0,
      [PAUSED]: 0,
    }
);

const tiles = computed(() => [
  { label: __("All open"), value: "" as const, count: summary.value.total },
  ...[OVERDUE, AT_RISK, ON_TRACK, PAUSED].map((state) => ({
    label: __(state),
    value: state,
    count: summary.value[state],
  })),
]);

const priorityOptions = computed(() => [
  { label: __("Any priority"), value: "" },
  ...(priorities.data || [])
    .filter((p) => !p.disabled)
    .map((p) => ({ label: __(p.name), value: p.name })),
]);

// Live countdown: the server sends seconds left at fetch time, and the
// table ticks them down locally between refreshes.
const now = useNow({ interval: 1000 });
const fetchedAt = ref(Date.now());

const liveTickets = computed(() => {
  const secondsSinceFetch = Math.max(
    (now.value.getTime() - fetchedAt.value) / 1000,
    0
  );
  return (monitor.data?.tickets || []).map((ticket: MonitorTicket) => {
    if (ticket.state === PAUSED) {
      return {
        ...ticket,
        liveRemaining: ticket.remaining_seconds,
        liveUsed: ticket.used_percent,
        liveState: PAUSED,
      };
    }
    const liveRemaining = ticket.remaining_seconds - secondsSinceFetch;
    // a target can pass between two refreshes
    const liveState: State = liveRemaining < 0 ? OVERDUE : ticket.state;
    return {
      ...ticket,
      liveRemaining,
      liveUsed: liveRemaining < 0 ? 100 : ticket.used_percent,
      liveState,
    };
  });
});

const visibleTickets = computed(() =>
  stateFilter.value
    ? liveTickets.value.filter((t) => t.liveState === stateFilter.value)
    : liveTickets.value
);

function remainingLabel(ticket: {
  liveRemaining: number;
  liveState: State;
}): string {
  const duration = formatDuration(Math.abs(ticket.liveRemaining));
  if (ticket.liveRemaining < 0) return __("{0} overdue", [duration]);
  if (ticket.liveState === PAUSED) return __("{0} left (paused)", [duration]);
  return __("{0} left", [duration]);
}

function formatDuration(totalSeconds: number): string {
  const seconds = Math.floor(totalSeconds);
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m`;
  return `${seconds % 60}s`;
}

const lastUpdated = computed(() => {
  if (!monitor.data) return "";
  const seconds = Math.round((now.value.getTime() - fetchedAt.value) / 1000);
  if (seconds < 10) return __("just now");
  if (seconds < 60) return __("{0}s ago", [seconds]);
  return __("{0}m ago", [Math.floor(seconds / 60)]);
});

// Auto refresh at the interval set in HD Settings (0 turns it off).
const { pause, resume } = useIntervalFn(
  () => {
    if (!monitor.loading) monitor.reload();
  },
  () => Math.max(settings.value.refresh_interval, 1) * 1000,
  { immediate: false }
);
watch(
  () => settings.value.refresh_interval,
  (interval) => (interval ? resume() : pause()),
  { immediate: true }
);

function openTicket(ticketId: string) {
  router.push({ name: "TicketAgent", params: { ticketId } });
}

usePageMeta(() => ({ title: __("SLA Monitor") }));
</script>
