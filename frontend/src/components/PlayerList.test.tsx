import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { PlayerList } from "./PlayerList";
import { usePlayerStore } from "../stores/playerStore";

beforeEach(() => {
  usePlayerStore.setState({ collaborators: [] });
});

describe("PlayerList", () => {
  it("renders nothing when collaborators is empty", () => {
    const { container } = render(<PlayerList />);
    expect(container.firstChild).toBeNull();
  });

  it("renders username for each collaborator", () => {
    usePlayerStore.setState({
      collaborators: [
        { userId: "abc123", username: "alice", role: "builder" },
        { userId: "def456", username: "bob", role: "viewer" },
      ],
    });
    render(<PlayerList />);
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("renders avatar with first letter of username", () => {
    usePlayerStore.setState({
      collaborators: [{ userId: "uid1", username: "charlie", role: "builder" }],
    });
    render(<PlayerList />);
    expect(screen.getByText("c")).toBeInTheDocument();
  });

  it("same userId always produces the same avatar color", () => {
    const collaborator = { userId: "stable-id-001", username: "dana", role: "builder" as const };
    usePlayerStore.setState({ collaborators: [collaborator] });

    const { unmount } = render(<PlayerList />);
    const firstAvatar = screen.getByText("d").style.backgroundColor;
    unmount();

    usePlayerStore.setState({ collaborators: [collaborator] });
    render(<PlayerList />);
    const secondAvatar = screen.getByText("d").style.backgroundColor;

    expect(firstAvatar).toBe(secondAvatar);
    expect(firstAvatar).not.toBe("");
  });

  it("two collaborators with different userId palette indices produce different avatar colors", () => {
    // "aaa": 97+97+97=291, 291%6=3 → color index 3 (#f59e0b)
    // "b":   98,           98%6=2  → color index 2 (#ec4899)
    usePlayerStore.setState({
      collaborators: [
        { userId: "aaa", username: "xfirst", role: "builder" },
        { userId: "b", username: "xsecond", role: "builder" },
      ],
    });
    render(<PlayerList />);
    const avatars = document.querySelectorAll("[data-avatar='true']");
    expect(avatars).toHaveLength(2);
    expect((avatars[0] as HTMLElement).style.backgroundColor).not.toBe(
      (avatars[1] as HTMLElement).style.backgroundColor
    );
  });
});
