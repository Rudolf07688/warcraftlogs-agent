import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./ui/alert-dialog";

// Feature 010 / FR-006: the single in-app confirmation for irreversible deletes.
// Controlled: the caller owns the pending item and closes the dialog by clearing it.
// While `busy` (request in flight) the dialog refuses to close and both actions are
// disabled, so Escape / backdrop clicks during the request do nothing (spec edge case).

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  /** Names the affected item, e.g. "rudolf@example.com will no longer be able to sign in." */
  description: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onCancel();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={busy}
            onClick={(e) => {
              // Radix closes on Action click by default; the caller closes us instead,
              // once the request has resolved.
              e.preventDefault();
              void onConfirm();
            }}
          >
            {busy ? "Working…" : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
