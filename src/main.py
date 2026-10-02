from __future__ import annotations

import json
from datetime import datetime, timezone

from config import (
    INUNDATION_URL,
    LATEST_DIR,
    PRECIPITATION_URL,
    RAINFALL_CUMULATIVE_HOURS,
    RAW_DIR,
)

from wra_client import WRAClient


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def save_json(
    path,
    data,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_api(
    client: WRAClient,
    name: str,
    url: str,
    output_file,
    params: dict | None = None,
) -> dict:

    print()
    print("=" * 70)
    print(f"Testing WRA {name}")
    print("=" * 70)

    print(
        "[WRA] URL:",
        url,
    )

    if params is not None:

        print(
            "[WRA] params:",
            json.dumps(
                params,
                ensure_ascii=False,
                indent=2,
            ),
        )

    else:

        print(
            "[WRA] params: None"
        )


    try:

        result = client.get(
            url=url,
            output_file=output_file,
            params=params,
        )

        return {
            "success": True,
            "url": result.get(
                "url",
                url,
            ),
            "params": params,
            "result": result,
        }

    except Exception as exc:

        print()
        print(
            f"[WRA] {name} FAILED"
        )

        print(
            repr(exc)
        )

        return {
            "success": False,
            "url": url,
            "params": params,
            "error": str(exc),
        }


def main():

    print("=" * 70)
    print("Taoyuan Water Monitor")
    print("WRA API Diagnostic")
    print("=" * 70)


    LATEST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    client = WRAClient()


    # ==================================================
    # 1. Rainfall
    # ==================================================

    rainfall_params = {
        "cumulativeHours": int(
            RAINFALL_CUMULATIVE_HOURS
        )
    }


    print()
    print(
        "[CONFIG] RAINFALL_CUMULATIVE_HOURS =",
        RAINFALL_CUMULATIVE_HOURS,
    )


    rainfall = test_api(

        client=client,

        name="precipitation",

        url=PRECIPITATION_URL,

        output_file=(
            RAW_DIR
            / "rainfall.bin"
        ),

        params=rainfall_params,
    )


    # ==================================================
    # 2. Inundation
    # ==================================================

    inundation = test_api(

        client=client,

        name="inundation",

        url=INUNDATION_URL,

        output_file=(
            RAW_DIR
            / "inundation.bin"
        ),

        params=None,
    )


    # ==================================================
    # 3. Summary
    # ==================================================

    status = {

        "updated_at":
            now_iso(),

        "city":
            "桃園市",

        "mode":
            "diagnostic",

        "rainfall":
            rainfall,

        "inundation":
            inundation,
    }


    save_json(
        LATEST_DIR / "status.json",
        status,
    )


    print()
    print("=" * 70)
    print("Diagnostic summary")
    print("=" * 70)

    print(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2,
        )
    )


    rainfall_ok = (
        rainfall.get("success")
        is True
    )

    inundation_ok = (
        inundation.get("success")
        is True
    )


    if not rainfall_ok:

        print(
            "[ERROR] Rainfall API failed."
        )


    if not inundation_ok:

        print(
            "[ERROR] Inundation API failed."
        )


    if not (
        rainfall_ok
        and inundation_ok
    ):

        raise RuntimeError(
            "One or more WRA APIs failed. "
            "See diagnostic output above."
        )


    print()
    print(
        "All WRA APIs succeeded."
    )


if __name__ == "__main__":
    main()
