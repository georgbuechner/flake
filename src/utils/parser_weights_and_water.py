import pandas as pd
import random
import math
from datetime import datetime
from typing import List, Sequence, overload


@overload
def weight_male(age: int) -> float: ...


@overload
def weight_male(age: float) -> float | None: ...


def weight_male(age: float) -> float | None:
    if age >= 226.54:
        return 32
    elif 28.318 < age < 226.54:
        return 5.5683 * math.log(age - 17) + 2.2379
    elif 0 < age <= 28.318:
        return 0.520827952625 * age
    elif age <= 0:
        return 0
    return None  # should never happen


@overload
def weight_female(age: int) -> float: ...


@overload
def weight_female(age: float) -> float | None: ...


def weight_female(age: float) -> float | None:
    if age >= 227.437:
        return 21
    elif 24.836 < age < 227.437:
        return 2.326 * math.log(age - 19) + 8.58
    elif 0 < age <= 24.836:
        return 0.470333852275 * age
    elif age <= 0:
        return 0
    return None  # should never happen


def generate_raw_weight_list(age_days: int, sex: str, duration_days: int) -> List[float]:
    if sex == "M":
        weight_curve = weight_male
    else:
        weight_curve = weight_female
    start_weight = weight_curve(age_days)

    weight_list = [start_weight]

    for day in range(1, duration_days + 1):
        new_weight = weight_curve(age_days + day)
        weight_list.append(new_weight)

    return weight_list


def apply_weight_factor(weight_list: Sequence[float], weight_factor: float) -> List[float]:
    return list(map(lambda weight: weight * weight_factor, weight_list))


def apply_noise(
    weight_list: Sequence[float], noise_factor: float, apply_to_first_day: bool = True
) -> List[float]:
    if apply_to_first_day:
        first_day_noise = random.uniform(-noise_factor, noise_factor)
    else:
        first_day_noise = 0
    noisy_list = [weight_list[0] * (1 + first_day_noise)]
    for i in range(1, len(weight_list)):
        previous_weight = noisy_list[i - 1]
        current_weight = weight_list[i] * (1 + random.uniform(-noise_factor, noise_factor))
        noisy_list.append((previous_weight + current_weight) / 2)
    return noisy_list


def enumerate_blocks(bool_list: Sequence[bool]) -> List[int]:
    current_boolean = bool_list[0]
    enumerated_blocks = [0]
    length_counter = 0

    for boolean in bool_list[1:]:
        if boolean == current_boolean:
            length_counter += 1
        else:
            current_boolean = boolean
            length_counter = 0
        enumerated_blocks.append(length_counter)

    return enumerated_blocks


def oblique_throw(x: float, x_apex: float, y_apex: float) -> float:
    """
    Returns the y-value of x on the curve of an oblique throw, approaching point (x_apex, y_apex) from origin.
    Can be used to calculated a quadratic approach to a point (the apex).
    :param x: x-value, determines value that is returned
    :param y_apex: y-value of the apex of the oblique throw
    :param x_apex: x-value of the apex of the oblique throw
    :return: y-value of the given x-coordinate on the trajectory defined by the given apex coordinates
    """
    a = - y_apex / pow(x_apex, 2)
    b = 2 * y_apex / x_apex
    return a * pow(x, 2) + b * x


def quadratic_approach(y_start: float, x_value: float, x_max: float, y_end: float) -> float:
    """
    Calculate a quadratic approach from y_start to y_end over a distance x_max. The returned value is the y-value to the
    parameter x_value. To model this approach, one half of an oblique throw is used. The quadratic approach is the curve
    from the origin to the apex of the trajectory.
    :param y_start: Value at which the trajectory starts
    :param x_value: Determines which y-value from the trajectory is returned.
    :param x_max: Determines the length of the trajectory
    :param y_end: Value at which the trajectory ends
    :return: estimated weight on the given day during the initial period of water control
    """
    if x_value <= 0:
        return y_start
    elif x_value >= x_max:
        return y_end
    else:
        return y_start + oblique_throw(x_value, x_max, y_end - y_start)


def apply_water_control_mask(
    weight_list: Sequence[float],
    water_control_mask: Sequence[bool],
    target_weight_percentage: float = 0.85,
    days_until_target_weight: int = 3,
    days_until_normal_weight: int = 2
) -> List[float]:
    assert len(weight_list) == len(water_control_mask), \
        f"Weights and mask have unequal lengths! No alignment possible. " + \
        f"{len(weight_list)}, {len(water_control_mask)}"

    enumerated_mask = enumerate_blocks(water_control_mask)

    new_weight_list = [weight_list[0]]

    for day in range(1, len(weight_list)):
        normal_weight = weight_list[day]
        target_weight = normal_weight * target_weight_percentage

        if water_control_mask[day]:
            """
            Calculate the daily weight, when the mouse is put on water control. 
            Between the point where the mouse has just been put on water control and the 
            estimated arrival at the target_weight, there is a quadratic approach used to 
            calculate the daily weight. Outside the limits it returns the normal_weight 
            (before water control) or target_weight (during water control).
            """
            days_without_water = enumerated_mask[day]
            new_weight_list.append(
                quadratic_approach(
                    normal_weight, days_without_water, days_until_target_weight, target_weight
                )
            )
        else:
            """
            Calculate the daily weight, when the mouse is off water control. 
            Between the point where the mouse gets free access to water again and the time 
            where we expect it to have returned to normal_weight, there is a quadratic 
            approach used to calculate the daily weight. Outside the limits it returns the 
            target_weight (with water control) or normal_weight (after water control).
            """
            days_with_water = enumerated_mask[day]
            new_weight_list.append(
                quadratic_approach(
                    target_weight, days_with_water, days_until_normal_weight, normal_weight
                )
            )
    return new_weight_list


def generate_raw_water_control_mask(
    start_date: datetime,
    duration_days: int,
    free_weekend_chance: float = 1,
    consecutive_free_weekends: bool = True,
) -> List[bool]:
    # Water Restriction Creating
    end_date = start_date + pd.Timedelta(duration_days-1, unit='D')
    day_list = pd.date_range(start=start_date, end=end_date).tolist()


    had_a_free_weekend = False
    weekend_value = False

    water_control_mask = []
    for date in day_list:
        if date.weekday() in (6, 0):
            if random.uniform(0, 1) <= free_weekend_chance:
                if had_a_free_weekend and not consecutive_free_weekends:
                    weekend_value = True
                    had_a_free_weekend = False
                else:
                    weekend_value = False
                    had_a_free_weekend = True
            else:
                weekend_value = True
                had_a_free_weekend = False
            water_control_mask.append(weekend_value) 
        else:
            water_control_mask.append(True) 
        # print(date, date.weekday(), " -> ", water_control_mask[-1])
    return water_control_mask


def apply_surgery_periods(
    start_date: datetime,
    water_control_mask: List[bool],
    surgery_dates: Sequence[datetime],
    pre_surgery_days: int = 3,
    min_post_surgery_days: int = 3,
    start_next_monday: bool = True,
) -> List[bool]:
    modified_water_control_mask = water_control_mask.copy()

    for surgery_date in surgery_dates:
        position = (surgery_date - start_date).days
        if position > len(modified_water_control_mask)-1 or position < 0:
            continue

        modified_water_control_mask[position] = False

        for day in range(1, pre_surgery_days + 1):
            pre_surgery_position = position - day
            if pre_surgery_position >= 0:
                modified_water_control_mask[pre_surgery_position] = False

        days_before_monday = 6 - start_date.weekday()
        if start_next_monday and days_before_monday > min_post_surgery_days:
            post_surgery_days = days_before_monday

        else:
            post_surgery_days = min_post_surgery_days

        for day in range(1, post_surgery_days + 1):
            post_surgery_position = position + day
            if post_surgery_position < len(modified_water_control_mask):
                modified_water_control_mask[post_surgery_position] = False

    return modified_water_control_mask


def apply_short_control_filter(
    water_control_mask: List[bool], min_block_length: int = 4, min_sum: int = 7
) -> List[bool]:
    filtered_water_control_mask = water_control_mask.copy()

    block_length_counter = 0
    for index, value in enumerate(filtered_water_control_mask):
        if value:
            block_length_counter += 1

        else:
            if 0 < block_length_counter < min_block_length:
                for i in range(1, block_length_counter + 1):
                    filtered_water_control_mask[index - i] = False
            block_length_counter = 0

    if sum([int(value) for value in filtered_water_control_mask]) < min_sum:
        filtered_water_control_mask = [False] * len(filtered_water_control_mask)

    return filtered_water_control_mask


def get_water_control_mask(start_date: datetime, duration: int, surgery_dates: Sequence[datetime]) -> List[bool]:
    water_control_mask = generate_raw_water_control_mask(start_date, duration)
    water_control_mask = apply_surgery_periods(start_date, water_control_mask, surgery_dates)
    water_control_mask = apply_short_control_filter(water_control_mask)
    return water_control_mask

def get_estimated_weight_list(
    age: int, sex: str, duration: int, water_control_mask: List[bool], start_weight: float
) -> List[float]:
    # Calculate weight factor
    weight_factor = 1 + random.uniform(-0.1, 0.1)
    if start_weight != -1:
        weight_curve = weight_male if sex == "M" else weight_female
        weight_factor = float(start_weight) / weight_curve(age)
    estimated_weight_list = generate_raw_weight_list(age, sex, duration)
    estimated_weight_list = apply_water_control_mask(estimated_weight_list, water_control_mask)
    estimated_weight_list = apply_weight_factor(estimated_weight_list, weight_factor)
    return estimated_weight_list
