import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toolbar } from "./Toolbar";
import { useCityStore } from "../stores/cityStore";

beforeEach(() => {
  useCityStore.setState({ activeViewMode: "base" });
});

describe("Toolbar — tool buttons", () => {
  it("renders all 6 tool buttons", () => {
    render(<Toolbar />);
    expect(screen.getByText("R")).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
    expect(screen.getByText("I")).toBeInTheDocument();
    expect(screen.getByText("🛣️")).toBeInTheDocument();
    // ⚡ appears in both tool group and view mode group
    expect(screen.getAllByText("⚡").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("🔨")).toBeInTheDocument();
  });

  it("tool buttons do not call setViewMode when clicked", () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    fireEvent.click(screen.getByText("R"));
    expect(setViewMode).not.toHaveBeenCalled();
  });
});

describe("Toolbar — view mode buttons", () => {
  it("renders all 4 view mode buttons", () => {
    render(<Toolbar />);
    expect(screen.getByText("Base")).toBeInTheDocument();
    // ⚡ appears in tools AND view modes — use getAllByText
    expect(screen.getAllByText("⚡")).toHaveLength(2);
    expect(screen.getByText("🌫️")).toBeInTheDocument();
    expect(screen.getByText("💧")).toBeInTheDocument();
  });

  it("active view mode button has blue background", () => {
    useCityStore.setState({ activeViewMode: "base" });
    render(<Toolbar />);
    const baseBtn = screen.getByTestId("viewmode-base");
    expect(baseBtn.style.backgroundColor).toBe("rgb(29, 78, 216)"); // #1d4ed8
  });

  it("inactive view mode buttons do not have blue background", () => {
    useCityStore.setState({ activeViewMode: "base" });
    render(<Toolbar />);
    const pollutionBtn = screen.getByTestId("viewmode-pollution");
    expect(pollutionBtn.style.backgroundColor).not.toBe("rgb(29, 78, 216)");
  });

  it("clicking Base calls setViewMode('base')", async () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    await userEvent.click(screen.getByTestId("viewmode-base"));
    expect(setViewMode).toHaveBeenCalledWith("base");
  });

  it("clicking electricity button calls setViewMode('electricity')", async () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    await userEvent.click(screen.getByTestId("viewmode-electricity"));
    expect(setViewMode).toHaveBeenCalledWith("electricity");
  });

  it("clicking pollution button calls setViewMode('pollution')", async () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    await userEvent.click(screen.getByTestId("viewmode-pollution"));
    expect(setViewMode).toHaveBeenCalledWith("pollution");
  });

  it("clicking water button calls setViewMode('water')", async () => {
    const setViewMode = vi.spyOn(useCityStore.getState(), "setViewMode");
    render(<Toolbar />);
    await userEvent.click(screen.getByTestId("viewmode-water"));
    expect(setViewMode).toHaveBeenCalledWith("water");
  });
});
