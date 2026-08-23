import { useState } from "react";
import { Plus, Check } from "lucide-react";
import { toast } from "sonner";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { errMsg } from "@/lib/api";

export const CategorySelect = ({ value, onChange, cats, addCategory, testId }) => {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  const save = async () => {
    if (!name.trim()) return setAdding(false);
    try {
      const c = await addCategory(name.trim());
      onChange(c.name);
      toast.success(`"${c.name}" added to the master list`);
      setName(""); setAdding(false);
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (adding)
    return (
      <div className="flex gap-2">
        <Input autoFocus className="h-11" placeholder="New category name" data-testid={`${testId}-new-input`}
               value={name} onChange={(e) => setName(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save(); } }} />
        <button type="button" onClick={save} data-testid={`${testId}-new-save`}
                className="px-3 border border-slate-300 rounded-md hover:bg-slate-50"><Check className="w-4 h-4" /></button>
      </div>
    );

  return (
    <div className="flex gap-2">
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-11 flex-1" data-testid={testId}><SelectValue placeholder="Category" /></SelectTrigger>
        <SelectContent>
          {cats.map((c) => <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>)}
        </SelectContent>
      </Select>
      <button type="button" onClick={() => setAdding(true)} data-testid={`${testId}-add-btn`}
              title="Add a new category to the master list"
              className="px-3 border border-slate-300 rounded-md hover:bg-slate-50"><Plus className="w-4 h-4" /></button>
    </div>
  );
};
