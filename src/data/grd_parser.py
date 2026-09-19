from pathlib import Path
import numpy as np
import pandas as pd


# IMD 1° × 1° temperature grid
LAT_START = 7.5
LON_START = 67.5
GRID_SIZE = 31
GRID_STEP = 1.0

# IMD uses 99.9 as the undefined/missing value
MISSING_VALUE = 99.9


def get_grid_coordinates():
    """
    Return latitude and longitude coordinates for the IMD 31x31 grid.
    """

    latitudes = LAT_START + np.arange(GRID_SIZE) * GRID_STEP
    longitudes = LON_START + np.arange(GRID_SIZE) * GRID_STEP

    return latitudes, longitudes


def read_grd_file(file_path):
    """
    Read an IMD yearly GRD file.

    Parameters
    ----------
    file_path : str or Path
        Path to the .GRD file.

    Returns
    -------
    numpy.ndarray
        Array with shape:

        (number_of_days, 31, 31)
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Each grid contains 31 x 31 float32 values.
    values_per_day = GRID_SIZE * GRID_SIZE

    # Read all binary values as 32-bit floats.
    data = np.fromfile(file_path, dtype=np.float32)

    # Make sure the file contains complete daily grids.
    if data.size % values_per_day != 0:
        raise ValueError(
            f"Invalid GRD file size. "
            f"{data.size} values cannot form complete "
            f"{GRID_SIZE}x{GRID_SIZE} daily grids."
        )

    number_of_days = data.size // values_per_day

    # Convert into:
    # days × latitude × longitude
    data = data.reshape(
        number_of_days,
        GRID_SIZE,
        GRID_SIZE
    )

    return data


def grd_to_dataframe(file_path, year):
    """
    Convert one yearly IMD GRD file into long-format DataFrame.

    Output columns:
        date
        latitude
        longitude
        max_temperature
    """

    data = read_grd_file(file_path)

    latitudes, longitudes = get_grid_coordinates()

    number_of_days = data.shape[0]

    dates = pd.date_range(
        start=f"{year}-01-01",
        periods=number_of_days,
        freq="D"
    )

    # Create coordinate grids.
    lat_grid, lon_grid = np.meshgrid(
        latitudes,
        longitudes,
        indexing="ij"
    )

    # Flatten everything into tabular format.
    df = pd.DataFrame({
        "date": np.repeat(dates, GRID_SIZE * GRID_SIZE),
        "latitude": np.tile(
            lat_grid.ravel(),
            number_of_days
        ),
        "longitude": np.tile(
            lon_grid.ravel(),
            number_of_days
        ),
        "max_temperature": data.reshape(-1)
    })

    # Replace IMD undefined values.
    df["max_temperature"] = df["max_temperature"].replace(
        MISSING_VALUE,
        np.nan
    )

    return df

def load_multiple_years(data_dir, start_year, end_year):
    """
    Load multiple yearly IMD GRD files into one DataFrame.
    """

    data_dir = Path(data_dir)

    yearly_data = []

    for year in range(start_year, end_year + 1):

        file_path = data_dir / f"{year}.GRD"

        print(f"Processing {year}...")

        yearly_df = grd_to_dataframe(
            file_path=file_path,
            year=year
        )

        yearly_data.append(yearly_df)

        print(
            f"  Days: {yearly_df['date'].nunique():,}"
            f" | Rows: {len(yearly_df):,}"
        )

    combined_df = pd.concat(
        yearly_data,
        ignore_index=True
    )

    return combined_df