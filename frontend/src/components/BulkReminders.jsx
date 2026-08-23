import { useState } from "react";
import { MessageCircle, Send, Check, Users } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { money } from "@/lib/format";
import { openWhatsApp, openSms } from "@/lib/notify";

export const BulkReminders = ({ rows, buildMessage }) => {
  const unpaid = rows.filter((r) => r.net > 0 && r.owner_phone);
  const missing = rows.filter((r) => r.net > 0 && !r.owner_phone);
  const [sent, setSent] = useState([]);

  const mark = (id) => setSent((s) => (s.includes(id) ? s : [...s, id]));
  const next = unpaid.find((r) => !sent.includes(r.flat_id));

  const send = (r, channel) => {
    if (channel === "sms") openSms(r.owner_phone, buildMessage(r));
    else openWhatsApp(r.owner_phone, buildMessage(r));
    mark(r.flat_id);
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" data-testid="bulk-reminders-btn">
          <Users className="w-4 h-4 mr-2" /> Remind all unpaid ({unpaid.length})
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl" data-testid="bulk-reminders-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Send dues reminders</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-500 -mt-2">
          {sent.length} of {unpaid.length} sent. Each one opens WhatsApp or your SMS app with the message ready —
          nothing is sent from the server, so it costs nothing.
        </p>

        {next && (
          <div className="mt-4 border border-slate-900 rounded-md p-4 bg-slate-50" data-testid="bulk-next-card">
            <div className="label-caps">Next up</div>
            <div className="flex items-center justify-between gap-3 mt-2">
              <div>
                <div className="font-semibold text-slate-900">Flat {next.flat_number} · {next.owner_name}</div>
                <div className="mono text-sm text-red-600">{money(next.net)} due · {next.owner_phone}</div>
              </div>
              <div className="flex gap-2">
                <Button onClick={() => send(next, "whatsapp")} data-testid="bulk-send-whatsapp-btn"
                        className="bg-emerald-600 hover:bg-emerald-700 text-white">
                  <MessageCircle className="w-4 h-4 mr-2" /> WhatsApp
                </Button>
                <Button onClick={() => send(next, "sms")} variant="outline" data-testid="bulk-send-sms-btn">
                  <Send className="w-4 h-4 mr-2" /> SMS
                </Button>
              </div>
            </div>
          </div>
        )}

        <div className="mt-4 max-h-64 overflow-y-auto">
          <table className="data-table">
            <thead><tr><th>Flat</th><th>Owner</th><th className="text-right">Due</th><th>Phone</th><th /></tr></thead>
            <tbody>
              {unpaid.map((r) => (
                <tr key={r.flat_id} data-testid={`bulk-row-${r.flat_number}`}>
                  <td className="font-semibold">{r.flat_number}</td>
                  <td>{r.owner_name}</td>
                  <td className="num text-red-600">{money(r.net)}</td>
                  <td className="mono text-slate-500">{r.owner_phone}</td>
                  <td className="text-right">
                    {sent.includes(r.flat_id) ? (
                      <span className="inline-flex items-center gap-1 text-xs text-emerald-700" data-testid={`bulk-sent-${r.flat_number}`}>
                        <Check className="w-3.5 h-3.5" /> sent
                      </span>
                    ) : (
                      <div className="flex justify-end gap-1.5">
                        <button onClick={() => send(r, "whatsapp")} data-testid={`bulk-whatsapp-${r.flat_number}`}
                                aria-label={`WhatsApp ${r.owner_name}`}
                                className="p-2 border border-slate-300 rounded-md text-emerald-700 hover:bg-emerald-50">
                          <MessageCircle className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => send(r, "sms")} data-testid={`bulk-sms-${r.flat_number}`}
                                aria-label={`SMS ${r.owner_name}`}
                                className="p-2 border border-slate-300 rounded-md text-slate-700 hover:bg-slate-100">
                          <Send className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {!unpaid.length && (
                <tr><td colSpan={5} className="text-sm text-slate-500">Everyone with a phone number is settled.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {missing.length > 0 && (
          <p className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2"
             data-testid="bulk-missing-phones">
            No phone number for flat{missing.length > 1 ? "s" : ""} {missing.map((r) => r.flat_number).join(", ")} —
            add it in Building Setup.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
};
