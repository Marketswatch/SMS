"""Calculation & reconciliation engine for SocietyHub.

All money rounded to 2 decimals at presentation boundaries only.
"""

RECURRING_TYPES = ["cleaning", "sweeper", "security", "electricity", "misc"]
ADHOC_TYPES = ["maintenance"]


def r2(x):
    return round(float(x or 0) + 0.0, 2)


def compute_statement(flats, meters, readings, tankers, charges, payments, carry_in):
    """Pure function. All args are plain dicts/lists with string ids.

    Returns full period statement.
    """
    n = len(flats) or 1
    flat_ids = [f["id"] for f in flats]
    flat_by_id = {f["id"]: f for f in flats}

    # --- water purchased ---
    total_litres = sum(float(t.get("qty_sump", 0)) + float(t.get("qty_syntex", 0)) for t in tankers)
    total_tips = sum(float(t.get("tips_amount", 0) or 0) for t in tankers)
    # A tanker's true cost = lorry amount + tips paid to the crew. Both form the per-litre price.
    total_spend = sum(float(t.get("amount", 0)) for t in tankers) + total_tips
    avg_cost = (total_spend / total_litres) if total_litres > 0 else 0.0

    # --- consumption ---
    reading_by_meter = {rd["meter_id"]: rd for rd in readings}
    meter_rows = []
    consumption_by_flat = {fid: 0.0 for fid in flat_ids}
    flags = []
    for m in meters:
        rd = reading_by_meter.get(m["id"], {})
        opening = float(rd.get("opening", m.get("opening", 0)) or 0)
        closing = rd.get("closing", None)
        cons = 0.0
        flagged = False
        if closing is not None and closing != "":
            closing = float(closing)
            if closing < opening:
                flagged = True
                flags.append({
                    "type": "meter_rollback",
                    "meter_id": m["id"],
                    "meter_label": m.get("label"),
                    "flat_id": m.get("flat_id"),
                    "message": f"Closing ({closing}) < opening ({opening}) for {m.get('label')} — meter reset/replacement? Review.",
                })
            else:
                cons = closing - opening
        else:
            closing = None
        if m.get("flat_id") in consumption_by_flat:
            consumption_by_flat[m["flat_id"]] += cons
        holder = flat_by_id.get(m.get("flat_id"), {})
        meter_rows.append({
            "meter_id": m["id"], "label": m.get("label"), "flat_id": m.get("flat_id"),
            "flat_number": holder.get("number", ""), "floor": holder.get("floor", ""),
            "owner_name": holder.get("owner_name", ""),
            "opening": opening, "closing": closing, "consumption": cons, "flagged": flagged,
        })

    for mr in meter_rows:
        mr["charge"] = r2(mr["consumption"] * avg_cost)

    total_consumed = sum(consumption_by_flat.values())
    reserve_litres = total_litres - total_consumed
    reserve_value = reserve_litres * avg_cost
    reserve_share = reserve_value / n
    if reserve_litres < 0:
        flags.append({
            "type": "negative_reserve",
            "message": f"Drawdown: consumption exceeds purchase by {abs(round(reserve_litres,2))} L. Tank reserve is being depleted.",
        })

    # --- charges split ---
    recurring_items = [c for c in charges if c.get("charge_type") in RECURRING_TYPES]
    adhoc_items = [c for c in charges if c.get("charge_type") in ADHOC_TYPES]
    recurring_total = sum(float(c.get("amount", 0)) for c in recurring_items)
    adhoc_total = sum(float(c.get("amount", 0)) for c in adhoc_items)
    recurring_share = recurring_total / n
    adhoc_share = adhoc_total / n

    # --- contributions ---
    contributions = {fid: 0.0 for fid in flat_ids}
    contribution_detail = {fid: [] for fid in flat_ids}
    for t in tankers:
        pid = t.get("payer_flat_id")
        amt = float(t.get("amount", 0))
        if pid in contributions and amt:
            contributions[pid] += amt
            contribution_detail[pid].append({"source": "tanker", "label": f"Tanker {t.get('date','')}",
                                             "amount": amt, "paid_by": t.get("payer_type", "owner")})
        tip_pid = t.get("tips_payer_flat_id") or pid
        tip_amt = float(t.get("tips_amount", 0) or 0)
        if tip_pid in contributions and tip_amt:
            contributions[tip_pid] += tip_amt
            contribution_detail[tip_pid].append({"source": "tips", "label": f"Tips {t.get('date','')}",
                                                 "amount": tip_amt, "paid_by": t.get("tips_payer_type", "owner")})
    for c in charges:
        pid = c.get("payer_flat_id")
        amt = float(c.get("amount", 0))
        if pid in contributions and amt:
            contributions[pid] += amt
            contribution_detail[pid].append({"source": c.get("charge_type"), "label": c.get("description") or c.get("charge_type"),
                                             "amount": amt, "paid_by": c.get("payer_type", "owner")})

    # --- payments recorded ---
    received = {fid: 0.0 for fid in flat_ids}
    received_by_tenant = {fid: 0.0 for fid in flat_ids}
    received_by_owner = {fid: 0.0 for fid in flat_ids}
    payouts = {fid: 0.0 for fid in flat_ids}
    last_paid_on = {fid: "" for fid in flat_ids}
    for p in payments:
        fid = p.get("flat_id")
        if fid not in received:
            continue
        amt = float(p.get("amount", 0))
        if p.get("direction") == "payout":
            payouts[fid] += amt
        else:
            received[fid] += amt
            d = str(p.get("date") or "")
            if d > last_paid_on[fid]:
                last_paid_on[fid] = d
            if p.get("payer_type") == "tenant":
                received_by_tenant[fid] += amt
            else:
                received_by_owner[fid] += amt

    rows = []
    for f in flats:
        fid = f["id"]
        cons = consumption_by_flat.get(fid, 0.0)
        water_own = cons * avg_cost
        water_cost = water_own + reserve_share
        base = water_cost + recurring_share + adhoc_share
        carry = float(carry_in.get(fid, 0) or 0)
        net = base - contributions[fid] + carry - received[fid] + payouts[fid]
        rows.append({
            "flat_id": fid,
            "flat_number": f.get("number"),
            "floor": f.get("floor", ""),
            "owner_name": f.get("owner_name"),
            "owner_phone": f.get("owner_phone", ""),
            "tenant_name": f.get("tenant_name"),
            "tenant_phone": f.get("tenant_phone", ""),
            "consumption": r2(cons),
            "water_own_cost": r2(water_own),
            "reserve_share": r2(reserve_share),
            "water_cost": r2(water_cost),
            "recurring_share": r2(recurring_share),
            "maintenance_share": r2(adhoc_share),
            "base_cost": r2(base),
            "contributions": r2(contributions[fid]),
            "contribution_detail": contribution_detail[fid],
            "carry_in": r2(carry),
            "received": r2(received[fid]),
            "received_by_tenant": r2(received_by_tenant[fid]),
            "received_by_owner": r2(received_by_owner[fid]),
            "payouts": r2(payouts[fid]),
            "net": r2(net),
            "status": "owes" if r2(net) > 0 else ("owed" if r2(net) < 0 else "settled"),
            "last_paid_on": last_paid_on[fid],
            "payment_status": "paid" if r2(net) <= 0.005 else ("partial" if received[fid] > 0 else "pending"),
        })

    totals = {
        "flat_count": len(flats),
        "tanker_count": len(tankers),
        "metered_charges": r2(total_consumed * avg_cost),
        "total_litres": r2(total_litres),
        "total_water_spend": r2(total_spend),
        "total_tips": r2(total_tips),
        "avg_cost_per_litre": round(avg_cost, 4),
        "total_consumed": r2(total_consumed),
        "reserve_litres": r2(reserve_litres),
        "reserve_value": r2(reserve_value),
        "reserve_share": r2(reserve_share),
        "recurring_total": r2(recurring_total),
        "recurring_share": r2(recurring_share),
        "maintenance_total": r2(adhoc_total),
        "maintenance_share": r2(adhoc_share),
        "billable_total": r2(sum(x["base_cost"] for x in rows)),
        "total_contributions": r2(sum(x["contributions"] for x in rows)),
        "total_received": r2(sum(x["received"] for x in rows)),
        "total_payouts": r2(sum(x["payouts"] for x in rows)),
        "total_carry_in": r2(sum(x["carry_in"] for x in rows)),
        "total_owes": r2(sum(x["net"] for x in rows if x["net"] > 0)),
        "total_owed": r2(abs(sum(x["net"] for x in rows if x["net"] < 0))),
        "net_position": r2(sum(x["net"] for x in rows)),
    }

    return {
        "rows": rows,
        "totals": totals,
        "meters": meter_rows,
        "flags": flags,
        "recurring_items": recurring_items,
        "adhoc_items": adhoc_items,
    }
