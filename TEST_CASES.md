# NYC Payroll Data Agent Test Cases

## 1. Schema Grounding
*   **TC-01: Highest Paid Employee**
    *   *Question:* "Who has the highest base salary?"
    *   *Expected:* `SELECT first_name, last_name, base_salary FROM payroll ORDER BY base_salary DESC LIMIT 1`
*   **TC-02: Agency Aggregation**
    *   *Question:* "Which agency has the most employees?"
    *   *Expected:* `GROUP BY agency_name ORDER BY count(*) DESC`

## 2. Ambiguity & Docs
*   **TC-03: Ambiguous 'Pay'**
    *   *Question:* "Show me the total pay for John Doe."
    *   *Expected:* Agent checks docs to see if "Total Pay" is a column or a calculation (sum of gross, OT, other).
    *   *Action:* `SELECT regular_gross_paid + total_ot_paid + total_other_pay ...`

## 3. Self-Correction
*   **TC-04: Misspelled Agency**
    *   *Question:* "Average salary in 'Children Services'"
    *   *Scenario:* Agent queries `WHERE agency_name = 'Children Services'`, gets 0 rows.
    *   *Recovery:* Agent tries `LIKE '%Children%'` and finds 'ADMIN FOR CHILDREN'S SVCS'.

## 4. Memory
*   **TC-05: Borough Preference**
    *   *User:* "When I say 'Manhattan', filter by work_location_borough = 'M'."
    *   *User (later):* "Show me top earners in Manhattan."
    *   *Expected:* Agent applies `WHERE work_location_borough = 'M'`.
