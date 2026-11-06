/**
 * @jest-environment jsdom
 */
import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { CurrencyInput, parseAmount } from "../currency-input";

describe("CurrencyInput reads an amount the same way while typing and after", () => {
  it.each([
    ["$10,000", 10000], ["10000", 10000], ["-10,000", 10000], ["1,234.50", 1234.5], ["", undefined],
  ])("%s", (text, expected) => {
    expect(parseAmount(text)).toBe(expected);
    const onChange = jest.fn();
    render(<CurrencyInput aria-label="amount" value={undefined} onChange={onChange} />);
    const input = screen.getByLabelText("amount");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: text } });
    if (text) expect(onChange).toHaveBeenLastCalledWith(expected);
    fireEvent.blur(input);
    expect(onChange).toHaveBeenLastCalledWith(expected);
  });
});
