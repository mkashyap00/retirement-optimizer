import type { PairedComparison } from "@/lib/types";

/** One vocabulary for paired verdicts, everywhere (the recommendation's
 *  point of view). "Too close to distinguish" is not "equivalent": only a
 *  declared materiality threshold earns that. */
export const VERDICT_LABEL: Record<PairedComparison["verdict"], string> = {
  winner: "Recommendation ahead",
  alternative: "Alternative ahead",
  unresolved: "Too close to distinguish",
  equivalent: "Practically equivalent",
};

/** The plain meaning of each "close" verdict; the statistics behind them
 *  belong in the details. */
export const EQUIVALENT_MEANING =
  "The results are similar enough to treat these options alike under the model’s comparison threshold.";
export const UNRESOLVED_MEANING =
  "These simulations don’t give us enough evidence to say which option is better.";
export const WINNER_MEANING = "These simulations provide evidence favoring the recommendation.";
export const ALTERNATIVE_MEANING = "These simulations provide evidence favoring the alternative.";
