<template>
  <div
    class="flex flex-wrap items-center gap-2 px-3 sm:px-5 pt-3"
    data-testid="ticket-list-filters"
  >
    <TextInput
      class="w-full sm:w-64"
      type="text"
      :model-value="search"
      :placeholder="__('Search ID, subject or email')"
      :debounce="400"
      @update:model-value="onSearch"
    >
      <template #prefix>
        <LucideSearch class="size-4 text-ink-gray-5" />
      </template>
    </TextInput>

    <Select
      class="w-full sm:w-40"
      :model-value="status"
      :options="statusOptions"
      :placeholder="__('Status')"
      @update:model-value="(v) => setCondition('status', v ? ['=', v] : null)"
    />

    <Select
      class="w-full sm:w-36"
      :model-value="priority"
      :options="priorityOptions"
      :placeholder="__('Priority')"
      @update:model-value="(v) => setCondition('priority', v ? ['=', v] : null)"
    />

    <Combobox
      class="w-full sm:w-44"
      trigger="button"
      :model-value="assignee"
      :options="assigneeOptions"
      :placeholder="__('Assignee')"
      @update:model-value="onAssignee"
    />

    <DateRangePicker
      class="w-full sm:w-56"
      :model-value="dateRange"
      variant="outline"
      :placeholder="__('Opened between')"
      :format="'MMM D, YYYY'"
      @update:model-value="onDateRange"
    >
      <template #prefix>
        <LucideCalendar class="size-4 text-ink-gray-5 me-2" />
      </template>
    </DateRangePicker>

    <Button
      v-if="activeCount > 0"
      variant="ghost"
      :label="__('Clear ({0})', [activeCount])"
      icon-left="lucide-x"
      @click="clearAll"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * Dedicated filter bar for the agent ticket list: search, status, priority,
 * assignee and opening date. It reads and writes the same filter conditions
 * as the generic Filter control, so both stay in sync and the result can be
 * saved into a view like any other filter. Conditions on other fields are
 * left untouched.
 */
import { useAgentStore } from "@/stores/agent";
import { useTicketPriorityStore } from "@/stores/ticketPriority";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { __ } from "@/translation";
import { normalizeFilters } from "@/components/view-controls/filter";
import {
  Button,
  Combobox,
  DateRangePicker,
  Select,
  TextInput,
} from "frappe-ui";
import { computed, onMounted, ref, watch } from "vue";

type Condition = [string, string, any];

const props = defineProps<{
  /** current list filters, in any shape normalizeFilters accepts */
  filters: any;
}>();

const emit = defineEmits<{
  (event: "apply", conditions: Condition[]): void;
}>();

// Pseudo field resolved on the server (helpdesk.api.doc.handle_search_filter)
const SEARCH_FIELD = "__search";
const DATE_FIELD = "opening_date";
const ASSIGN_FIELD = "_assign";
const MANAGED_FIELDS = [
  SEARCH_FIELD,
  "status",
  "priority",
  ASSIGN_FIELD,
  DATE_FIELD,
];

// Assignee choices that are not a single agent
const ME = "@me";
const UNASSIGNED = "__unassigned";

const { statuses } = useTicketStatusStore();
const { priorities } = useTicketPriorityStore();
const agentStore = useAgentStore();

onMounted(() => {
  if (!agentStore.agents.data && !agentStore.agents.loading) {
    agentStore.agents.fetch();
  }
});

const conditions = computed<Condition[]>(() => normalizeFilters(props.filters));

function findCondition(field: string): Condition | undefined {
  return conditions.value.find((c) => c[0] === field);
}

// Search box keeps its own text while typing; it follows the filters when
// they change from elsewhere (view switch, "Clear all").
const search = ref("");
watch(
  () => findCondition(SEARCH_FIELD)?.[2],
  (value) => {
    search.value = String(value ?? "").replaceAll("%", "");
  },
  { immediate: true }
);

const status = computed(() => equalsValue("status"));
const priority = computed(() => equalsValue("priority"));

function equalsValue(field: string): string {
  const condition = findCondition(field);
  return condition && condition[1] === "=" ? condition[2] : "";
}

const assignee = computed(() => {
  const condition = findCondition(ASSIGN_FIELD);
  if (!condition) return "";
  const [, operator, value] = condition;
  if (String(operator).toLowerCase() === "not like") return UNASSIGNED;
  const user = String(value ?? "").replaceAll("%", "");
  return user;
});

const dateRange = computed<string[]>(() => {
  const condition = findCondition(DATE_FIELD);
  if (!condition || condition[1] !== "between") return [];
  return Array.isArray(condition[2]) ? condition[2] : [];
});

const statusOptions = computed(() => [
  { label: __("Any status"), value: "" },
  ...(statuses.data || [])
    .filter((s) => s.enabled !== 0)
    .map((s) => ({ label: __(s.label_agent), value: s.label_agent })),
]);

const priorityOptions = computed(() => [
  { label: __("Any priority"), value: "" },
  ...(priorities.data || [])
    .filter((p) => !p.disabled)
    .map((p) => ({ label: __(p.name), value: p.name })),
]);

const assigneeOptions = computed(() => [
  { label: __("Anyone"), value: "" },
  { label: __("Assigned to me"), value: ME },
  { label: __("Unassigned"), value: UNASSIGNED },
  ...(agentStore.dropdown || []),
]);

const activeCount = computed(
  () => conditions.value.filter((c) => MANAGED_FIELDS.includes(c[0])).length
);

/** Replace (or drop, when `operatorValue` is null) the condition on `field`. */
function setCondition(field: string, operatorValue: [string, any] | null) {
  const next = conditions.value.filter((c) => c[0] !== field);
  if (operatorValue) next.push([field, ...operatorValue]);
  emit("apply", next);
}

function onSearch(value: string) {
  search.value = value;
  const term = (value || "").trim();
  setCondition(SEARCH_FIELD, term ? ["like", term] : null);
}

function onAssignee(value: string | null) {
  if (!value) return setCondition(ASSIGN_FIELD, null);
  if (value === UNASSIGNED) {
    // _assign is a JSON list; any assignee adds a quoted name, while an
    // unassigned ticket holds NULL, "" or "[]".
    return setCondition(ASSIGN_FIELD, ["not like", '%"%']);
  }
  // "%@me%" is swapped for the session user on the server
  setCondition(ASSIGN_FIELD, ["like", `%${value}%`]);
}

function onDateRange(range: string[] | null) {
  setCondition(
    DATE_FIELD,
    range?.length === 2 && range[0] && range[1] ? ["between", range] : null
  );
}

function clearAll() {
  search.value = "";
  emit(
    "apply",
    conditions.value.filter((c) => !MANAGED_FIELDS.includes(c[0]))
  );
}
</script>
