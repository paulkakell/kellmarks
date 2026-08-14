from __future__ import annotations

import base64
import zlib
from pathlib import Path

ROOT = Path.cwd().resolve()


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    content = path.read_text(encoding="utf-8")
    if old not in content:
        raise SystemExit(f"release fix pattern missing in {relative}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_once("docs/server/app.py", '                if any(\n                    not label\n                    or len(label) > 63\n                    or not re.fullmatch(\n                        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label\n                    )\n                    for label in labels\n                ):\n                    raise RuntimeError(f"invalid trusted host: {raw_host}")\n', '                if any(\n                    not label\n                    or len(label) > 63\n                    or not re.fullmatch(\n                        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label\n                    )\n                    for label in labels\n                ):\n                    raise RuntimeError(\n                        f"invalid trusted host: {raw_host}"\n                    ) from None\n')
    replace_once(
        "tests/test_security.py",
        "from __future__ import annotations\n\n\nTOKEN = ",
        "from __future__ import annotations\n\nTOKEN = ",
    )
    replace_once("tests/test_security.py", 'def test_sensitive_runtime_files_are_not_static(client) -> None:\n    assert client.get("/assets/data.json").status_code == 404\n    assert client.get("/server/app.py").status_code == 404\n    assert client.get("/server/requirements.lock").status_code == 404\n    assert client.get("/assets/sample-data.json").status_code == 200\n', 'def test_sensitive_runtime_files_are_not_static(client) -> None:\n    paths = {\n        "/assets/data.json": 404,\n        "/server/app.py": 404,\n        "/server/requirements.lock": 404,\n        "/assets/sample-data.json": 200,\n    }\n    for path, expected_status in paths.items():\n        response = client.get(path)\n        try:\n            assert response.status_code == expected_status\n        finally:\n            response.close()\n')
    replace_once(
        "tests/test_store.py",
        "import pytest\n\nimport app as kellmarks\n",
        "import app as kellmarks\nimport pytest\n",
    )
    replace_once(
        "tests/test_validation.py",
        "import pytest\n\nimport app as kellmarks\n",
        "import app as kellmarks\nimport pytest\n",
    )
    test_data = zlib.decompress(base64.b64decode('eNq9WOtu4kYU/s9TjEZaybRATLKbpEip1F2l7VarRErSlbossgb7GFzMjHdmTEKivEnfpi/WM+MLNoHgkLYIBTOc+/nmmzMJpZgTzwtTnUrwPBLNEyE1YZwLzXQkuGq1QiMTMA06mkMhUXzvEPP3XnBotQrlJCFMkRnE8ZzJmSrWk6UGpVutVgAhMY8e8EUkBZ8D195YiBgY9xImVcQnzlzwGSwTpv1pm3R/JBfoYtAi+Kr80gsgRiMOfX95+cm7Pr+5+XjxC+0QySJj5OxnFitoWy2mFGAQZVQ94916faJ9I1Nok0jZB6scCkkWLE4xfU4c2kchqvFH8/nH+bX5EJy2s/jWY1SgN8Vo7bVLjcbxPRuZa0IJTdbm4eLSRhaG/1NoldLZyrca+qNKzC2aFM283kZ6muOlZ3oJyrlKuZE4l1LIDpkbc2c0B001vQYF3AbBiGuYgPQYDzxfLfaE4seLm32QiM7Xdd91SB/fbpucnZF3W4tZV6In9DVuTpq6UbAA/sJ25QV+pl3Phdc0sn7/pSgCfQvA9w1rKxI+XH/eBwkIvXVdhyJgWRpr2mnbNlUXttalbgMZyrD1reiQjp5KAPqiIHK3aMSS362wH7mdyobScKc9JJAosOeH54sFSOXpZQKehG9pJCHwsD4TPc02muBailg5a1vraVi5tvXgXNhsaBhBHNASvZRua/zKzucytjoKlJbYni0gqPk+qTve32VRjyZOKSG05hcRlaufWdbdPwy486FhEIhs3PbEnyI10n+rDDkEGgUQRxzeuD+NJbBZNYBDt4bCVMYbQCgS843FXpQsjr0o4MxCUC25ZncemKB245ALOUfL9+BNtU6MJ4fSSjOy/V1BYyML5kkNDg6Gh67bHwTj08GgPxqcvn17dICbeppvv7I+O+WtZPvl/t///deHX8+venDH5kkMB1sd3/Fud+xPQXZnC7YSr/gtRxNsNCjFJtmMUppaOc21e76YHzAyNn29nUbYyIT5SC+dHSpv7u+NSgLSx2N8p/zgB/MyGhYh5PerT4VOBYH7IDlPs2KljuUNhc9HrSqBsskG6Ko0MUM0cqeasgSUBS4EE3gJYNG0ssxpmzocNZKnt0LODhT4qYz0skOwzMpsIqxfZmaFjZokXbWBFjr52mh/rogjpYkIScbWajNnrGXwQPE2QweEMoLfiTFBH/8jvlxzPaR3lHxHTvujeo/NrKsRkV4hnzU7xQA8xULwcIaPx8yf2T6n2l/vcvE7QZo5dA+Pu+5pt39047oD+/6yk3rKEPKjtDBoe1p8aW7ElLjLuuZaSF9vrJJR/3BwZDJat1qhpA3SX6pEhBcgHImwUi/32nWP13xXsyguwT1zRY6UCI1V7WT+ehKSGPnLoV8M13xv+0Lb7Z6+j3goTA7F1bmHDa5fSrRc4vlkm5+wZSxY8IQTvAlwkNmCJYONx1cuBMGW9AtXOQoK8cpIkedaGuphtaRWZufgPNClr9hISL54VXx+CtoS6iu8prwk08Yu6ZhhrMFrkv3t+vKCiPGf4OtmbvPGO8M6d2T/TckGFy1wMJJCbJq4I27X8vNiHRf7ER/GFYEi8xRJeAyEZVy6I5s84FzZeXjEy9Mr6sgFXnYkED3ddvHf6npofD88jnBe3T8AWZTh69D9OlrVgjds7npMNG8UHdm6WF0LANyxDyuSQ4EBya5fq0Ud6RjM+mV9HScLs1oMP4Zi8gGopo0nFIoNR9nao/1bBoq3NHPWbqaNDHlZws7Qhjsq25ozxpqlITWwxGrSkeG+w2dF8+rQ0dAdDU3uVsemv7tx1ya4p1cMhtNnYXdHj2rpNQXsBreZBYKDcJONUvNawsI6/weSTQ3k'))
    (ROOT / "tests/test_configuration.py").write_bytes(test_data)
    print("applied release-gate fixes and configuration regression tests")


if __name__ == "__main__":
    main()
