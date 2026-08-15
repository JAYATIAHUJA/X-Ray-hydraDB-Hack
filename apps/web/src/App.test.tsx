import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

test("renders the three-lens shell and fixture ghost finding", async () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "X-Ray" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Org/ })).toHaveAttribute("aria-current", "page");
  expect(screen.getAllByText("Maya Chen")).toHaveLength(2);
  expect(screen.getByText("How HydraDB Answered This")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /Faultlines/ }));

  expect(screen.getByRole("button", { name: /Faultlines/ })).toHaveAttribute("aria-current", "page");
  expect(screen.getByText("payments-api -> ledger-worker")).toBeInTheDocument();
});
