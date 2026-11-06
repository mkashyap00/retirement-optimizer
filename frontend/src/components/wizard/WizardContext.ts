import React from "react";
import type { FieldErrors } from "./schemas";

export interface WizardErrorContextValue {
  showErrors: boolean;
  errors: FieldErrors;
}

export const WizardErrorContext = React.createContext<WizardErrorContextValue>({
  showErrors: false,
  errors: {},
});
