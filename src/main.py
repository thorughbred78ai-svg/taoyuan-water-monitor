from pathlib import Path

from config import (
    PRECIPITATION_API,
    INUNDATION_API,
    OUTPUT_DIR,
)

from wra_client import WRAClient


def main():

    output = Path(OUTPUT_DIR)
    output.mkdir(
        parents=True,
        exist_ok=True
    )

    client = WRAClient()

    print("Downloading precipitation...")

    rainfall = client.get_raster(
        PRECIPITATION_API,
        output / "rainfall.raw"
    )

    print(
        "Rainfall:",
        rainfall["content_type"]
    )

    print("Downloading inundation...")

    inundation = client.get_raster(
        INUNDATION_API,
        output / "inundation.raw"
    )

    print(
        "Inundation:",
        inundation["content_type"]
    )


if __name__ == "__main__":
    main()
