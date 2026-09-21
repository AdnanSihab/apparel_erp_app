### Apparel Track

Optimizing Inventory Tracking and the Reorder Process in an Apparel Supply Chain.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app apparel_track
```

### Tests and demonstration

All tests live in `apparel_track/tests/`:

| File | What it covers |
|---|---|
| `test_table_10_1.py` | T1-T10 from Table 10.1 of the report, plus follow-on checks (runs on the site, rolled back) |
| `test_rules.py` | the reorder level formula and the reliability score (no database) |
| `demo_scenarios.py` | terminal walkthrough of 14 scenarios with PASS/FAIL (rolled back) |
| `seed_demo_data.py` | builds the presentation data (`seed`) and removes it (`reset`) |

```bash
bench --site apparel-site run-tests --app apparel_track
bench --site apparel-site execute apparel_track.tests.demo_scenarios.run
bench --site apparel-site execute apparel_track.tests.seed_demo_data.seed
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/apparel_track
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade
### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs ERPNext and this app and runs the test suite. Manual only: Actions tab -> CI -> Run workflow.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
