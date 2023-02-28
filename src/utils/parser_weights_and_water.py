import pandas as pd
import random
import math
from typing import Dict, List, Tuple


def weight_male(age):
    if age >= 226.54:
        return 32
    elif 28.318 < age < 226.54:
        return 5.5683 * math.log(age - 17) + 2.2379
    elif 0 < age <= 28.318:
        return 0.520827952625 * age
    elif age <= 0:
        return 0
    return None  # should never happen


def weight_female(age):
    if age >= 227.437:
        return 21
    elif 24.836 < age < 227.437:
        return 2.326 * math.log(age - 19) + 8.58
    elif 0 < age <= 24.836:
        return 0.470333852275 * age
    elif age <= 0:
        return 0
    return None  # should never happen


def generate_raw_weight_list(age_days, sex, duration_days):
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


def apply_weight_factor(weight_list, weight_factor):
    return list(map(lambda weight: weight * weight_factor, weight_list))


def apply_noise(weight_list, noise_factor, apply_to_first_day=True):
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


def enumerate_blocks(bool_list):
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


def oblique_throw(x, x_apex, y_apex):
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


def quadratic_approach(y_start, x_value, x_max, y_end):
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
    weight_list, 
    water_control_mask, 
    target_weight_percentage=0.85, 
    days_until_target_weight=3,
    days_until_normal_weight=2
):
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


def generate_raw_water_control_mask(start_date, duration_days, free_weekend_chance=0.4,
                                    consecutive_free_weekends=False, sacrificed=True):
    # Water Restriction Creating
    end_date = start_date + pd.Timedelta(duration_days, unit='D')
    day_list = pd.date_range(start=start_date, end=end_date).tolist()

    water_control_mask = []

    had_a_free_weekend = False

    weekend_counter = 0
    weekend_value = False

    for date in day_list:
        if date.weekday() in (4, 5, 6) and weekend_counter == 0:
            weekend_counter = 7 - date.weekday()

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

        if weekend_counter > 0:
            water_control_mask.append(weekend_value)
            weekend_counter -= 1
        else:
            water_control_mask.append(True)

    if sacrificed:
        final_weekday = end_date.weekday()
        if final_weekday <= 2:
            final_weekday += 3
            # 3 because: we start from 1 and have to go at least to 3 to include the final weekend. Monday = 0
        for i in range(1, min(len(water_control_mask) + 1, final_weekday + 2)):
            # +1 to account for weekday shift from 0 to 1 and +1 more to include last value
            water_control_mask[-i] = False  # During the last week and the previous weekend the mouse receives water

    if (len(water_control_mask) - sum(water_control_mask)) < 7:
        water_control_mask = [False] * len(water_control_mask)

    return water_control_mask


def apply_surgery_periods(start_date, water_control_mask, surgery_dates, pre_surgery_days=3,
                          min_post_surgery_days=3, start_next_monday=True):
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


def apply_short_control_filter(water_control_mask, min_block_length=4, min_sum=7):
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


def get_water_control_mask(start_date, duration, surgery_dates, sacrificed):
    water_control_mask = generate_raw_water_control_mask(start_date, duration, sacrificed=sacrificed)
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
