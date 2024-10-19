from ortools.sat.python import cp_model

SHIFTS = ['D', 'N', 'B']

def create_shift_schedule(workers, days,
                          non_working_days, non_day_shifts, days_off_per_worker,
                          consec_weight, eq_weight, max_consec_weight,
                          variability_weight, perfection_weight):
    model = cp_model.CpModel()

    # Variables
    x = {}
    work = {}
    no_shift = {}
    day_shifts = {}
    night_shifts = {}
    backup_shifts = {}
    total_shifts = {}
    total_number_deviations = {}
    type_number_deviations = {}
    imperfect_shifts = []
    overlimit_vars = []
    ideal_penalty_vars = []

    total_days_number = len(days)
    total_staff_number = len(workers)
    total_shifts_assigned = total_days_number * len(SHIFTS)
    average_shifts = total_shifts_assigned // len(workers)
    average_shifts_by_type = average_shifts // 3

    for w in workers:
        for d in days:
            for s in SHIFTS:
                x[w, d, s] = model.NewBoolVar(f'x[{w},{d},{s}]')

    # Hard constraints
    for d in days:
        # All shifts per day
        for s in SHIFTS:
            model.AddExactlyOne(x[w, d, s] for w in workers)

    for w in workers:
        for d in days:
            # Omit non-working days
            if d in non_working_days.get(w, []):
                for s in SHIFTS:
                    model.Add(x[w, d, s] == 0)
            if d in non_day_shifts.get(w, []):
                model.Add(x[w, d, 'D'] == 0)
            # Forbid to have nights before days and two nights in a row
            if d >= 2:
                model.Add(x[w, d, 'D'] + x[w, d - 1, 'N'] <= 1)
                model.Add(x[w, d, 'N'] + x[w, d - 1, 'N'] <= 1)
                model.Add(x[w, d, 'D'] + x[w, d - 1, 'B'] <= 1)

    # Soft constraints
    # Forbid to have more than three shifts in a row
    for w in workers:
        for d in days:
            work[(w, d)] = model.NewBoolVar(f'work[{w},{d}]')
            no_shift[(w, d)] = model.NewBoolVar(f'no_shift[{w},{d}]')
            model.Add(work[(w, d)] == sum(x[(w, d, s)] for s in SHIFTS))
            model.Add(no_shift[(w, d)] + work[(w, d)] == 1)
    for w in workers:
        for d in range(1, total_days_number - 3):
            overlimit = model.NewBoolVar(f'overlimit[{w},{d}]')
            workload = sum(work[(w, d + i)] for i in range(4))
            # Define overlimit to be 1 if workload == 4
            model.Add(workload >= 4).OnlyEnforceIf(overlimit)
            model.Add(workload <= 3).OnlyEnforceIf(overlimit.Not())
            overlimit_vars.append(overlimit)

    # Equalize all shifts (total and by types)
    for w in workers:
        total_shifts[w] = model.NewIntVar(0, total_days_number * len(SHIFTS), f'total_shifts[{w}]')
        day_shifts[w] = model.NewIntVar(0, total_days_number * len(SHIFTS), f'day_shifts[{w}]')
        night_shifts[w] = model.NewIntVar(0, total_days_number * len(SHIFTS), f'night_shifts[{w}]')
        backup_shifts[w] = model.NewIntVar(0, total_days_number * len(SHIFTS), f'backup_shifts[{w}]')
        model.Add(total_shifts[w] == sum(x[(w, d, s)] for d in days for s in SHIFTS))
        model.Add(day_shifts[w] == sum(x[w, d, "D"] for d in days))
        model.Add(night_shifts[w] == sum(x[w, d, "N"] for d in days))
        model.Add(backup_shifts[w] == sum(x[w, d, "B"] for d in days))
    for w in workers:
        doff = days_off_per_worker.get(w, 0)
        doff_per_type = doff // 3
        deviation = model.NewIntVar(0, total_shifts_assigned, f'deviation[{w}]')
        deviation_tp_n = model.NewIntVar(0, total_shifts_assigned, f'deviation[{w}]')
        deviation_tp_d = model.NewIntVar(0, total_shifts_assigned, f'deviation[{w}]')
        deviation_tp_b = model.NewIntVar(0, total_shifts_assigned, f'deviation[{w}]')
        model.Add(deviation >= (total_shifts[w] + doff) - average_shifts)
        model.Add(deviation >= average_shifts - (total_shifts[w] - doff))
        model.Add(deviation_tp_d >= (day_shifts[w] + doff_per_type) - average_shifts_by_type)
        model.Add(deviation_tp_d >= average_shifts_by_type - (day_shifts[w] + doff_per_type))
        model.Add(deviation_tp_b >= (backup_shifts[w] + doff_per_type) - average_shifts_by_type)
        model.Add(deviation_tp_b >= average_shifts_by_type - (backup_shifts[w] + doff_per_type))
        model.Add(deviation_tp_n >= (night_shifts[w] + doff_per_type) - average_shifts_by_type)
        model.Add(deviation_tp_n >= average_shifts_by_type - (night_shifts[w] + doff_per_type))
        total_number_deviations[w] = deviation
        type_number_deviations[w] = deviation_tp_d + deviation_tp_n + deviation_tp_b

    # Minimize consecutive shifts
    max_consecutive = model.NewIntVar(0, total_days_number, 'max_consecutive')
    for w in workers:
        for d in range(1, total_days_number - 3):
            consecutive_work = sum(x[w, d + i, s] for i in range(4) for s in SHIFTS)
            model.Add(consecutive_work <= max_consecutive)

    # Minimize repetitions
    for w in workers:
        for d in range(2, total_days_number):
            for s in SHIFTS:
                same_shift = model.NewBoolVar(f'same_shift[{w},{d},{s}]')
                model.Add(same_shift <= x[w, d - 1, s])
                model.Add(same_shift <= x[w, d, s])
                model.Add(same_shift >= x[w, d - 1, s] + x[w, d, s] - 1)
                imperfect_shifts.append(same_shift)
        # Prefer DN_B
        for d in range(4, total_days_number):
            for s in SHIFTS:
                ideal = model.NewBoolVar(f'ideal[{w},{d},{s}]')
                model.Add(ideal <= x[w, d - 3, 'D'])
                model.Add(ideal <= x[w, d - 2, 'N'])
                model.Add(ideal <= no_shift[w, d - 1])
                model.Add(ideal <= x[w, d, 'B'])
                model.Add(ideal >= x[w, d - 3, 'D'] + x[w, d - 2, 'N'] + no_shift[w, d - 1] + x[w, d, 'B'] - 3)

                ideal_penalty = model.NewBoolVar(f'ideal_penalty[{w},{d - 3}]')
                model.Add(ideal_penalty + ideal == 1)
                ideal_penalty_vars.append(ideal_penalty)


    # Objective function
    model.Minimize(
        eq_weight * sum(total_number_deviations.values()) +
        eq_weight * sum(type_number_deviations.values()) +
        consec_weight * sum(overlimit_vars) +
        max_consec_weight * max_consecutive +
        variability_weight * sum(imperfect_shifts) +
        perfection_weight * sum(ideal_penalty_vars)
        )

    # Solve the model
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        schedule = {}
        for w in workers:
            schedule[w] = {}
            schedule[w]["days"] = []
            schedule[w]["D"] = 0
            schedule[w]["N"] = 0
            schedule[w]["B"] = 0
            schedule[w]["total"] = 0
            for d in days:
                current_shift = " "
                for s in SHIFTS:
                    if solver.Value(x[w, d, s]):
                        current_shift = s
                        schedule[w][s] += 1
                        schedule[w]["total"] += 1
                schedule[w]["days"].append(current_shift)
        return schedule
    else:
        print('No feasible solution found.')
        return None
    

workers = ['W1', 'W2', 'W3', 'W4', 'W5']
days = list(range(1, 32))
non_working_days = {
    'W1': [1, 5, 8, 12],
    'W4': list(range(15, 31))
}
non_day_shifts = {
    'W2': [2, 7, 9, 14],
    'W3': [1, 22, 30],
    'W5': [15, 27]
}
days_off = {
    'W4': 15
}

schedule = create_shift_schedule(workers, days, non_working_days, non_day_shifts, days_off, 10, 20, 10, 5, 5)


if schedule:
    for w in workers:
        shifts = f"{w}\t\t\t{'|'.join(schedule[w]['days'])}\t"\
                f"D:{schedule[w]['D']}, N:{schedule[w]['N']}, B:{schedule[w]['B']}, "\
                f"T:{schedule[w]['total']}"
        print(shifts)