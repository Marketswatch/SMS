import { Images } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { API_BASE } from "@/lib/api";
import { money } from "@/lib/format";

const GROUPS = [
  { key: "bill", label: "Bill / Invoice" },
  { key: "in_progress", label: "Work in progress" },
  { key: "completed", label: "Work completed" },
];

const token = () => localStorage.getItem("sh_token");

const Tile = ({ m }) => (
  <a href={`${API_BASE}/files/${m.id}?auth=${token()}`} target="_blank" rel="noreferrer"
     className="block aspect-square rounded-md overflow-hidden border border-slate-200 bg-slate-100">
    {m.content_type?.startsWith("video/") ? (
      <span className="w-full h-full flex items-center justify-center text-xs text-slate-500">VIDEO</span>
    ) : (
      <img src={`${API_BASE}/files/${m.id}?auth=${token()}`} alt="" className="w-full h-full object-cover" />
    )}
  </a>
);

export const WorkGallery = ({ charge, testId }) => {
  const media = charge.media || [];
  const uncategorised = media.filter((m) => !GROUPS.some((g) => g.key === m.category));

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button data-testid={testId} title="View photo gallery"
                className="inline-flex items-center gap-1.5 text-xs px-2 py-1 border border-slate-300 rounded-md hover:bg-slate-50">
          <Images className="w-3.5 h-3.5" /> {media.length}
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto" data-testid={`${testId}-dialog`}>
        <DialogHeader>
          <DialogTitle className="font-display">{charge.description || charge.charge_type}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-500 -mt-2">
          {money(charge.amount)} · {charge.date || "—"} · {media.length} file{media.length === 1 ? "" : "s"}
        </p>
        <div className="grid sm:grid-cols-3 gap-5 mt-4">
          {GROUPS.map((g) => {
            const items = media.filter((m) => m.category === g.key);
            return (
              <div key={g.key} data-testid={`${testId}-group-${g.key}`}>
                <div className="label-caps mb-2">{g.label} <span className="text-slate-400">({items.length})</span></div>
                {items.length ? (
                  <div className="grid grid-cols-2 gap-2">{items.map((m) => <Tile key={m.id} m={m} />)}</div>
                ) : (
                  <div className="border border-dashed border-slate-300 rounded-md p-6 text-center text-xs text-slate-400">
                    No photos yet
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {uncategorised.length > 0 && (
          <div className="mt-6">
            <div className="label-caps mb-2">Other files ({uncategorised.length})</div>
            <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
              {uncategorised.map((m) => <Tile key={m.id} m={m} />)}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
