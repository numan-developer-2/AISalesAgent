import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ActivityChart, OutcomeChart, SourceChart } from "./AnalyticsCharts";

describe("Accessible analytics charts", () => {
  it("shows exact daily values on keyboard focus and moves between dates", async () => {
    render(
      <ActivityChart
        rows={[
          { date: "2026-11-13", conversations: 2, leads: 1 },
          { date: "2026-11-14", conversations: 5, leads: 3 },
        ]}
      />,
    );
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", {
        name: "November 13, 2026: 2 conversations, 1 leads",
      }),
    );
    expect(screen.getByRole("tooltip")).toHaveTextContent("November 13, 2026");
    await user.keyboard("{ArrowRight}");
    expect(
      screen.getByRole("button", {
        name: "November 14, 2026: 5 conversations, 3 leads",
      }),
    ).toHaveFocus();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Conversations 5");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Leads 3");
  });

  it("lets the user toggle series while keeping at least one visible", async () => {
    render(
      <ActivityChart
        rows={[{ date: "2026-11-14", conversations: 1, leads: 1 }]}
      />,
    );
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: "Leads" }),
    );
    expect(
      screen.getByRole("button", { name: "Leads" }),
    ).toHaveAttribute("aria-pressed", "false");
    expect(
      screen.getByRole("button", { name: "Conversations" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Leads" }),
    );
    expect(
      screen.getByRole("button", { name: "Conversations" }),
    ).toBeEnabled();
  });

  it("handles empty and zero-count periods without inventing activity", () => {
    const { rerender, container } = render(<ActivityChart rows={[]} />);
    expect(
      screen.getByText("No activity recorded in this period."),
    ).toBeInTheDocument();
    rerender(
      <ActivityChart
        rows={[{ date: "2026-11-14", conversations: 0, leads: 0 }]}
      />,
    );
    expect(
      screen.getByText("No activity yet in this period"),
    ).toBeInTheDocument();
    expect(container.querySelector(".activity-bar")).toHaveAttribute(
      "height",
      "0",
    );
    rerender(
      <OutcomeChart
        counts={{
          sessions: 0,
          engaged: 0,
          contactable: 0,
          progressing: 0,
          booked: 0,
          won: 0,
        }}
      />,
    );
    expect(
      [
        ...container.querySelectorAll<HTMLElement>(".visual-bar-track > span"),
      ].every((el) => el.style.width === "0%"),
    ).toBe(true);
    expect(container.innerHTML).not.toContain("NaN");
  });

  it("aggregates campaign rows by source and updates the displayed metric", async () => {
    const counts = {
      sessions: 4,
      engaged: 2,
      contactable: 1,
      progressing: 0,
      booked: 0,
      won: 0,
    };
    render(
      <SourceChart
        sources={[
          { ...counts, source: "google", medium: "cpc", campaign: "one" },
          { ...counts, source: "google", medium: "organic", campaign: "two" },
          { ...counts, source: "direct", medium: "none", campaign: "none" },
        ]}
      />,
    );
    const user = userEvent.setup();
    let rows = within(
      screen.getByRole("list", { name: "Source contribution breakdown" }),
    ).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("google8");
    expect(screen.getByText("12 sessions")).toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Source chart metric"),
      "contactable",
    );
    rows = within(
      screen.getByRole("list", { name: "Source contribution breakdown" }),
    ).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("google2");
    await user.selectOptions(
      screen.getByLabelText("Source chart metric"),
      "booked",
    );
    expect(
      screen.getByText("No booked recorded for these sources."),
    ).toBeInTheDocument();
    expect(screen.getByText("0 booked sessions")).toBeInTheDocument();
  });
});
