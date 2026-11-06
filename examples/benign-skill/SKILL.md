---
name: benign-skill
description: Generate a concise Markdown report from a user-supplied CSV file. Use when a user explicitly asks for a CSV summary report; decline unrelated requests.
license: MIT
metadata:
  author: sqsp-example-team
  version: "1.0.0"
---

# CSV summary helper

## Purpose and inputs

Summarize the supplied CSV in the assigned workspace. The input is the approved
inputs/example.csv file; the output is the approved outputs/report.md file.
No external tools or network access are required.

## Steps

1. Read only the CSV supplied by the user in the assigned inputs directory.
2. Validate the header using `references/INPUT_FORMAT.md`.
3. Count data rows and calculate the total of the numeric amount column.
4. Use `assets/report-template.md` to prepare the Markdown result.
5. Save the result as outputs/report.md in the assigned outputs directory.

## Errors and limitations

If the file is missing, the header is invalid, or an amount is not a number,
stop and return a clear validation error. Do not guess missing values.
If the approved output directory is unavailable, explain the failure and ask
the user to choose an approved directory. Reject requests outside this purpose.

## Example

Input: a CSV with two data rows, amounts 10 and 15.
Expected output: a Markdown report with `Rows: 2` and `Total amount: 25`.

The cases in `evals/cases.yaml` are synthetic fixtures. SQSP does not treat their
presence as evidence that a real host executed them successfully.
