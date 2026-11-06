import { planPayload } from "@/lib/planPayload";
import { useWizardStore } from "@/stores/wizardStore";
import type { HouseholdPayload } from "@/lib/types";

function form(settings: Partial<HouseholdPayload["settings"]>): HouseholdPayload {
  const data = useWizardStore.getState().data;
  return { ...data, settings: { ...data.settings, ...settings } };
}

test("a floor typed before switching back to keep spending the same is not saved", () => {
  expect(planPayload(form({ spending_rule: "fixed", spending_floor: 135000 })).settings.spending_floor)
    .toBeNull();
  expect(planPayload(form({ spending_rule: "guardrails", spending_floor: 135000 })).settings.spending_floor)
    .toBe(135000);
});
