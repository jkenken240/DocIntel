import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./ConfirmDialog";

function DialogHarness({ busy = false }: { busy?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Delete Atlas.pdf
      </button>
      <ConfirmDialog
        open={open}
        title="Delete Atlas.pdf?"
        description="This removes the document and dependent answers."
        confirmLabel="Delete document"
        busy={busy}
        onConfirm={vi.fn()}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}

describe("ConfirmDialog", () => {
  it("contains keyboard focus, dismisses with Escape, and restores focus", async () => {
    const user = userEvent.setup();
    render(<DialogHarness />);

    const trigger = screen.getByRole("button", { name: "Delete Atlas.pdf" });
    await user.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Delete Atlas.pdf?" });
    const close = screen.getByRole("button", { name: "Close confirmation" });
    const keep = screen.getByRole("button", { name: "Keep document" });
    const confirm = screen.getByRole("button", { name: "Delete document" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(keep).toHaveFocus();

    await user.tab();
    expect(confirm).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(confirm).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("does not dismiss a busy destructive action", async () => {
    const user = userEvent.setup();
    render(<DialogHarness busy />);

    await user.click(screen.getByRole("button", { name: "Delete Atlas.pdf" }));
    await user.keyboard("{Escape}");

    expect(screen.getByRole("dialog")).toBeVisible();
    expect(screen.getByRole("button", { name: "Keep document" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Close confirmation" })).toBeDisabled();
  });
});
