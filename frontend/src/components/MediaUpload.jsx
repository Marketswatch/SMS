import { useRef, useState } from "react";
import { Camera, Upload, MapPin, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, API_BASE } from "@/lib/api";

const getGps = () =>
  new Promise((resolve) => {
    if (!navigator.geolocation) return resolve({});
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: String(p.coords.latitude), lng: String(p.coords.longitude) }),
      () => resolve({}),
      { timeout: 6000 }
    );
  });

function useUploader(setMedia, category) {
  const [busy, setBusy] = useState(false);
  const handle = async (e, source) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    setBusy(true);
    const gps = await getGps();
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("source", source);
      if (gps.lat) fd.append("lat", gps.lat);
      if (gps.lng) fd.append("lng", gps.lng);
      try {
        const { data } = await api.post("/uploads", fd);
        setMedia((m) => [...m, category ? { ...data, category } : data]);
      } catch (err) {
        toast.error(errMsg(err));
      }
    }
    setBusy(false);
  };
  return { busy, handle };
}

const token = () => localStorage.getItem("sh_token");

const Thumb = ({ m, onRemove, testId }) => (
  <div className="relative w-20 h-20 rounded-md overflow-hidden border border-slate-200 bg-slate-100">
    {m.content_type?.startsWith("video/") ? (
      <div className="w-full h-full flex items-center justify-center text-[10px] text-slate-500">VIDEO</div>
    ) : (
      <img src={`${API_BASE}/files/${m.id}?auth=${token()}`} alt="" className="w-full h-full object-cover" />
    )}
    {m.lat && (
      <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-[8px] px-1 flex items-center gap-0.5">
        <MapPin className="w-2 h-2" /> {Number(m.lat).toFixed(3)},{Number(m.lng).toFixed(3)}
      </div>
    )}
    {onRemove && (
      <button type="button" onClick={onRemove} data-testid={testId}
              className="absolute top-0.5 right-0.5 bg-white/90 rounded-full p-0.5">
        <X className="w-3 h-3" />
      </button>
    )}
  </div>
);

export const MediaUpload = ({ media, setMedia, testId = "media", label = "Photos / Video (optional)", category }) => {
  const pickRef = useRef(null);
  const camRef = useRef(null);
  const { busy, handle } = useUploader(setMedia, category);
  const shown = category ? media.filter((m) => m.category === category) : media;

  return (
    <div>
      <div className="label-caps mb-2">{label}</div>
      <div className="flex gap-2">
        <button type="button" onClick={() => camRef.current?.click()} data-testid={`${testId}-camera-btn`}
                className="flex-1 h-11 flex items-center justify-center gap-2 text-sm font-medium border border-slate-300 rounded-md hover:bg-slate-50">
          <Camera className="w-4 h-4" /> Camera
        </button>
        <button type="button" onClick={() => pickRef.current?.click()} data-testid={`${testId}-upload-btn`}
                className="flex-1 h-11 flex items-center justify-center gap-2 text-sm font-medium border border-slate-300 rounded-md hover:bg-slate-50">
          <Upload className="w-4 h-4" /> Gallery
        </button>
      </div>
      <input ref={camRef} type="file" accept="image/*,video/*" capture="environment" hidden
             onChange={(e) => handle(e, "camera")} data-testid={`${testId}-camera-input`} />
      <input ref={pickRef} type="file" accept="image/*,video/*" multiple hidden
             onChange={(e) => handle(e, "upload")} data-testid={`${testId}-file-input`} />
      {busy && (
        <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Uploading…
        </div>
      )}
      {shown.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2" data-testid={`${testId}-thumbs`}>
          {shown.map((m, i) => (
            <Thumb key={m.id} m={m} testId={`${testId}-remove-${i}`}
                   onRemove={() => setMedia((arr) => arr.filter((x) => x.id !== m.id))} />
          ))}
        </div>
      )}
    </div>
  );
};

// Compact inline uploader for table rows (e.g. one meter's readings).
export const MediaMini = ({ media = [], setMedia, testId }) => {
  const pickRef = useRef(null);
  const camRef = useRef(null);
  const { busy, handle } = useUploader(setMedia);

  return (
    <div className="flex items-center gap-1.5">
      <button type="button" onClick={() => camRef.current?.click()} data-testid={`${testId}-camera-btn`}
              aria-label="Capture photo or video" title="Capture photo"
              className="p-2.5 border border-slate-300 rounded-md hover:bg-slate-50">
        <Camera className="w-4 h-4" />
      </button>
      <button type="button" onClick={() => pickRef.current?.click()} data-testid={`${testId}-upload-btn`}
              aria-label="Upload photo or video from gallery" title="Upload from gallery"
              className="p-2.5 border border-slate-300 rounded-md hover:bg-slate-50">
        <Upload className="w-4 h-4" />
      </button>
      <input ref={camRef} type="file" accept="image/*,video/*" capture="environment" hidden
             onChange={(e) => handle(e, "camera")} data-testid={`${testId}-camera-input`} />
      <input ref={pickRef} type="file" accept="image/*,video/*" multiple hidden
             onChange={(e) => handle(e, "upload")} data-testid={`${testId}-file-input`} />
      {busy && <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400" />}
      <div className="flex gap-1" data-testid={`${testId}-thumbs`}>
        {media.map((m, i) => (
          <div key={m.id} className="relative w-9 h-9 rounded border border-slate-200 overflow-hidden bg-slate-100">
            <a href={`${API_BASE}/files/${m.id}?auth=${token()}`} target="_blank" rel="noreferrer">
              {m.content_type?.startsWith("video/") ? (
                <span className="text-[7px] flex items-center justify-center h-full text-slate-500">VID</span>
              ) : (
                <img src={`${API_BASE}/files/${m.id}?auth=${token()}`} alt="" className="w-full h-full object-cover" />
              )}
            </a>
            <button type="button" data-testid={`${testId}-remove-${i}`}
                    onClick={() => setMedia((arr) => arr.filter((x) => x.id !== m.id))}
                    className="absolute -top-1 -right-1 bg-white border border-slate-200 rounded-full p-0.5">
              <X className="w-2.5 h-2.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

export const MediaThumbs = ({ media, showCategory }) => {
  if (!media?.length) return <span className="text-slate-300">—</span>;
  return (
    <div className="flex gap-1">
      {media.map((m) => (
        <a key={m.id} href={`${API_BASE}/files/${m.id}?auth=${token()}`} target="_blank" rel="noreferrer"
           title={showCategory && m.category ? m.category.replace("_", " ") : m.original_filename}
           className="block w-8 h-8 rounded border border-slate-200 overflow-hidden bg-slate-100">
          {m.content_type?.startsWith("video/") ? (
            <span className="text-[7px] flex items-center justify-center h-full text-slate-500">VID</span>
          ) : (
            <img src={`${API_BASE}/files/${m.id}?auth=${token()}`} alt="" className="w-full h-full object-cover" />
          )}
        </a>
      ))}
    </div>
  );
};
