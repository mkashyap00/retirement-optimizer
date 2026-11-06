"use client";

import { useContext, useState, useEffect } from "react";
import { Trash2, Plus } from "lucide-react";
import { useWizardStore } from "@/stores/wizardStore";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { CurrencyInput } from "@/components/ui/currency-input";
import { getPortfolio } from "@/lib/api";
import { WizardErrorContext } from "../WizardContext";
import { ACCOUNT_LABELS, OWNER_LABELS } from "@/lib/labels";
import { FieldLabel, FieldError, StepHeader, useCollapsed, money, EntrySummary } from "./shared";

// ---------------------------------------------------------------------------
// Step 3: Accounts
// ---------------------------------------------------------------------------

export function StepAccounts() {
  const data = useWizardStore((s) => s.data);
  const setField = useWizardStore((s) => s.setField);
  const addAccount = useWizardStore((s) => s.addAccount);
  const removeAccount = useWizardStore((s) => s.removeAccount);
  const { showErrors, errors } = useContext(WizardErrorContext);

  const accounts = data.accounts;
  const isJoint = data.household.filing_status === "joint";
  const accountHasError = (i: number) =>
    showErrors && Object.keys(errors).some((k) => k.startsWith(`accounts.${i}.`));
  // A Roth with money in it needs its opening year (the 5-year rule).
  const rowComplete = (a: (typeof accounts)[number]) =>
    (a.balance ?? 0) > 0 && (a.account_type !== "roth" || a.roth_opened_year != null);
  const accountComplete = (i: number) => rowComplete(accounts[i]) && !accountHasError(i);
  const accountRows = useCollapsed(() =>
    accounts.flatMap((a, i) => (rowComplete(a) ? [i] : [])));

  // Auto-fill taxable cost basis from an already-uploaded portfolio, so the
  // figure the tax projection uses (assemble.py sums taxable basis) doesn't
  // have to be typed twice. The simulation only cares about the TOTAL taxable
  // basis, so we fill the single taxable account when it's still blank; with
  // multiple taxable accounts the split is ambiguous, so we leave it.
  const [autofilled, setAutofilled] = useState<{
    index: number;
    value: number;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPortfolio()
      .then((p) => {
        if (cancelled) return;
        const taxableBasis = p.positions
          .filter((pos) => pos.account_type === "taxable")
          .reduce((sum, pos) => sum + (pos.cost_basis ?? 0), 0);
        if (taxableBasis <= 0) return;

        const store = useWizardStore.getState();
        const taxable = store.data.accounts
          .map((a, idx) => ({ a, idx }))
          .filter(({ a }) => a.account_type === "taxable");
        if (taxable.length !== 1) return; // ambiguous split — leave it
        if (taxable[0].a.basis) return; // don't clobber a typed value

        const value = Math.round(taxableBasis);
        store.setField(`accounts.${taxable[0].idx}.basis`, value);
        setAutofilled({ index: taxable[0].idx, value });
      })
      .catch(() => {
        /* no portfolio uploaded → nothing to fill */
      });
    return () => {
      cancelled = true;
    };
    // Run once on mount; reads/writes the store imperatively via getState.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Per-type totals
  const totals = { taxable: 0, traditional: 0, roth: 0 };
  for (const acct of accounts) {
    if (acct.account_type === "taxable") totals.taxable += acct.balance ?? 0;
    else if (acct.account_type === "traditional")
      totals.traditional += acct.balance ?? 0;
    else if (acct.account_type === "roth") totals.roth += acct.balance ?? 0;
  }

  function fmtTotals(n: number) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(n);
  }

  return (
    <div>
      <StepHeader
        title="Accounts"
        description="Add your investment and retirement accounts."
      />

      <p className="text-xs text-muted-foreground mb-3">
        Tip: upload your holdings on the <strong>Portfolio</strong> tab before
        this step and your taxable <strong>cost basis</strong> fills in here
        automatically.
      </p>

      <div className="flex flex-col gap-3">
        {accounts.map((acct, i) => accountComplete(i) && accountRows.isCollapsed(i) ? (
          <EntrySummary
            key={i}
            testId={`account-summary-${i}`}
            what={`account ${i + 1}`}
            text={
              `${ACCOUNT_LABELS[acct.account_type] ?? acct.account_type} · ` +
              `${OWNER_LABELS[acct.owner] ?? acct.owner} · ${money(acct.balance)}` +
              (acct.basis ? ` · basis ${money(acct.basis)}` : "") +
              (acct.account_type === "roth" && acct.roth_opened_year != null
                ? ` · opened ${acct.roth_opened_year}`
                : "")
            }
            onEdit={() => accountRows.expand(i)}
            onRemove={() => {
              accountRows.removed(i);
              removeAccount(i);
            }}
          />
        ) : (
          <div
            key={i}
            className="rounded-lg border border-border bg-card p-4 shadow-folio flex flex-col gap-3"
          >
            {/* Row header */}
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Account {i + 1}
              </span>
              <span className="flex gap-1 -mr-1">
                {accountComplete(i) && (
                  <Button variant="ghost" size="sm" onClick={() => accountRows.collapse(i)}>
                    Done
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    accountRows.removed(i);
                    removeAccount(i);
                  }}
                  aria-label={`Remove account ${i + 1}`}
                  className="text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" />
                  Remove
                </Button>
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {/* Account Type */}
              <div className="flex flex-col gap-1.5">
                <FieldLabel htmlFor={`acct-type-${i}`}>Account Type</FieldLabel>
                <Select
                  value={acct.account_type}
                  onValueChange={(val) =>
                    setField(`accounts.${i}.account_type`, val)
                  }
                >
                  <SelectTrigger id={`acct-type-${i}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="taxable">Taxable</SelectItem>
                    <SelectItem value="traditional">Traditional IRA/401k</SelectItem>
                    <SelectItem value="roth">Roth IRA/401k</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Owner */}
              <div className="flex flex-col gap-1.5">
                <FieldLabel htmlFor={`acct-owner-${i}`}>Owner</FieldLabel>
                <Select
                  value={acct.owner}
                  onValueChange={(val) =>
                    setField(`accounts.${i}.owner`, val)
                  }
                >
                  <SelectTrigger id={`acct-owner-${i}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="self">Self</SelectItem>
                    {isJoint && <SelectItem value="spouse">Spouse</SelectItem>}
                    <SelectItem value="joint">Joint</SelectItem>
                  </SelectContent>
                </Select>
                {showErrors && errors[`accounts.${i}.owner`] && (
                  <FieldError message={errors[`accounts.${i}.owner`]} />
                )}
              </div>

              {/* Balance */}
              <div className="flex flex-col gap-1.5">
                <FieldLabel
                  htmlFor={`acct-balance-${i}`}
                  tip="Current fair market value in dollars."
                >
                  Balance
                </FieldLabel>
                <CurrencyInput
                  id={`acct-balance-${i}`}
                  value={acct.balance}
                  onChange={(n) =>
                    setField(`accounts.${i}.balance`, n ?? 0)
                  }
                />
                {showErrors && errors[`accounts.${i}.balance`] && (
                  <FieldError message={errors[`accounts.${i}.balance`]} />
                )}
              </div>

              {/* Roth opened year — only for Roth accounts */}
              {acct.account_type === "roth" && (
                <div className="flex flex-col gap-1.5">
                  <FieldLabel
                    htmlFor={`acct-roth-year-${i}`}
                    tip="The year you first opened this Roth IRA or Roth 401(k). Required when the account has a balance: the 5-year rule requires the account to have been open at least 5 years before earnings can be withdrawn tax-free, and the plan warns when a withdrawal would come too soon."
                  >
                    Year Roth opened
                  </FieldLabel>
                  <Input
                    id={`acct-roth-year-${i}`}
                    type="number"
                    min={1998}
                    max={new Date().getFullYear()}
                    placeholder={`e.g. ${new Date().getFullYear() - 5}`}
                    value={acct.roth_opened_year ?? ""}
                    onChange={(e) =>
                      setField(
                        `accounts.${i}.roth_opened_year`,
                        e.target.value === "" ? null : Number(e.target.value)
                      )
                    }
                  />
                  {showErrors && errors[`accounts.${i}.roth_opened_year`] && (
                    <FieldError message={errors[`accounts.${i}.roth_opened_year`]} />
                  )}
                </div>
              )}

              {/* Cost Basis / After-Tax Basis — for taxable + traditional */}
              {(acct.account_type === "taxable" ||
                acct.account_type === "traditional") && (
                <div className="flex flex-col gap-1.5">
                  <FieldLabel
                    htmlFor={`acct-basis-${i}`}
                    tip={
                      acct.account_type === "traditional"
                        ? "If you made non-deductible contributions to a Traditional IRA, enter the cumulative amount from IRS Form 8606 line 14."
                        : "Total amount paid for the investments. Found on your brokerage statement as 'Cost Basis' or 'Adjusted Cost Basis.' The tax projection uses this figure to size capital gains — leaving it at 0 overstates your taxes. If you also upload holdings on the Portfolio tab, use the same total there; it drives the sell list and is reconciled against this number."
                    }
                  >
                    {acct.account_type === "traditional"
                      ? "After-tax basis (Form 8606)"
                      : "Cost Basis (used for the tax projection)"}
                  </FieldLabel>
                  <CurrencyInput
                    id={`acct-basis-${i}`}
                    value={acct.basis}
                    onChange={(n) => {
                      setField(`accounts.${i}.basis`, n ?? 0);
                      if (autofilled?.index === i) setAutofilled(null);
                    }}
                  />
                  {autofilled?.index === i && (
                    <p
                      className="text-xs text-emerald-700"
                      data-testid={`basis-autofilled-${i}`}
                    >
                      Auto-filled from your uploaded portfolio (
                      {fmtTotals(autofilled.value)}). Edit if it&apos;s wrong.
                    </p>
                  )}
                  {showErrors && errors[`accounts.${i}.basis`] && (
                    <FieldError message={errors[`accounts.${i}.basis`]} />
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        <Button
          variant="outline"
          onClick={addAccount}
          className="w-full border-dashed text-muted-foreground hover:text-foreground hover:border-primary"
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Account
        </Button>

        {/* Per-type totals footer */}
        {accounts.length > 0 && (
          <div className="rounded-md bg-muted/40 border border-border px-4 py-2.5 flex gap-6 text-xs">
            <span className="text-muted-foreground">
              Taxable:{" "}
              <strong className="text-foreground">
                {fmtTotals(totals.taxable)}
              </strong>
            </span>
            <span className="text-muted-foreground">
              Traditional:{" "}
              <strong className="text-foreground">
                {fmtTotals(totals.traditional)}
              </strong>
            </span>
            <span className="text-muted-foreground">
              Roth:{" "}
              <strong className="text-foreground">
                {fmtTotals(totals.roth)}
              </strong>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
