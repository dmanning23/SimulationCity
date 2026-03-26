import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { StatsBar } from "./StatsBar";
import { useCityStore } from "../stores/cityStore";

beforeEach(() => {
  useCityStore.setState({
    globalStats: { population: 0, treasury: 0, happiness: 50 },
  });
});

describe("StatsBar", () => {
  it("renders treasury with § prefix and locale formatting", () => {
    useCityStore.setState({
      globalStats: { population: 0, treasury: 10000, happiness: 50 },
    });
    render(<StatsBar />);
    expect(screen.getByText(/§10,000/)).toBeInTheDocument();
  });

  it("renders population as integer", () => {
    useCityStore.setState({
      globalStats: { population: 1240, treasury: 0, happiness: 50 },
    });
    render(<StatsBar />);
    expect(screen.getByText(/1240/)).toBeInTheDocument();
  });

  it("renders happiness as percentage", () => {
    useCityStore.setState({
      globalStats: { population: 0, treasury: 0, happiness: 72 },
    });
    render(<StatsBar />);
    expect(screen.getByText(/72%/)).toBeInTheDocument();
  });

  it("updates when globalStats changes in store", () => {
    render(<StatsBar />);
    act(() => {
      useCityStore.setState({
        globalStats: { population: 999, treasury: 5000, happiness: 88 },
      });
    });
    expect(screen.getByText(/§5,000/)).toBeInTheDocument();
    expect(screen.getByText(/999/)).toBeInTheDocument();
    expect(screen.getByText(/88%/)).toBeInTheDocument();
  });
});
