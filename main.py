from schedule_maker import create_shift_schedule, get_timetable
from yaml import safe_load
from calendar import monthrange
import csv
import datetime

start = datetime.datetime.now()

conditions = {}

with open("conditions.yaml", encoding="utf8") as condf:
    conditions = safe_load(condf)

debug = conditions.get("debug", False)

workers = conditions["employees"].keys()
month = conditions["month"]
year = conditions["year"]
tz = conditions["tz"]
example_dt = start.replace(year=year, month=month, day=1)
shift_start_hours = conditions["shift_start"]
month_info = monthrange(year, month)
first_day = month_info[0]
days = list(range(1, month_info[1] + 1))

non_working_days = {k: v.get("days_off", []) for k, v in conditions["employees"].items()}
non_day_shifts = {k: v.get("no_day_duty", []) for k, v in conditions["employees"].items()}
days_off = {k: v.get("pto", 0) for k, v in conditions["employees"].items()}

time_limit = conditions.get("time_limit", 60)
print(f"Calculating schedule (time limit is {time_limit}s)")
schedule = create_shift_schedule(workers, days, non_working_days, non_day_shifts, days_off,
                                 consec_weight=10,
                                 eq_weight=20,
                                 max_consec_weight=20,
                                 variability_weight=5,
                                 perfection_weight=10,
                                 time_limit=time_limit)

if schedule:
    timetable = get_timetable(schedule, year, month, shift_start_hours, tz)
    if debug:
        print("Debug output:")
        print(f"Schedule for {datetime.datetime.strftime(example_dt, "%B")}"
            f" {year}:")
        for w in workers:
            shifts = f"{w: <30}{'|'.join(schedule[w]['days'])}\t"\
                    f"D:{schedule[w]['D']}, N:{schedule[w]['N']}, B:{schedule[w]['B']}, "\
                    f"T:{schedule[w]['total']}"
            print(shifts)
        print("\nTimetable:")
        for t in timetable:
            shift = f"{t["start_display"]: <15} - {t["end_display"]: <15} — {t["login"]: <30}"
            if not t["is_primary"]:
                shift += "(Backup)"
            print(shift)
    print("Writing output files")
    with open(f"timetable_{year}_{month: <2}.csv", "w+", encoding="utf8", newline="") as outf:
        csvw = csv.writer(outf, delimiter=",")
        csvw.writerow(("start", "end", "name", "is_primary"))
        for t in timetable:
            csvw.writerow((t["start_iso"], t["end_iso"], t["login"], t["is_primary"]))
        print("CSV done")
    with open(f"timetable_{year}_{month: <2}.out.md", "w+", encoding="utf8") as outf:
        outf.write(f"## {example_dt.strftime('%B %Y')}\n")
        outf.write(f"|Name|{'|'.join([str(x) for x in days])}|\n")
        outf.write(f"|---|{' :----:|'*len(days)}\n")
        outf.write(f"||{'|'.join([example_dt.replace(day=x).strftime("%a") for x in days])}|\n")
        for w in sorted(workers):
            outf.write(f"|кто:{w}|{'|'.join(schedule[w]['days'])}|\n")
        outf.write("\n")
        outf.write("|Name|Total|🌞|🌜|☎️|✈️|\n")
        outf.write("|---|---|---|---|---|---|\n")
        for w in sorted(workers):
            outf.write(f"|кто:{w}|{schedule[w]['total']}|{schedule[w]['D']}|{schedule[w]['N']}"
                       f"|{schedule[w]['B']}|{days_off[w]}|\n")
        print("MD done")
    print("Done!")

end = datetime.datetime.now()

print(f"Finished in {int((end-start).total_seconds()//60)}m "
      f"{int((end-start).total_seconds()%60): <2}s")