# Testing Guide - Session Persistence & Attendance Workflow

## Quick Start

### Prerequisites
1. Ensure your database is initialized
2. Have at least one employee user with hourly_rate set

### Running the Application
```bash
streamlit run main.py
```

---

## Test Scenarios

### 1. Session Persistence (Browser Refresh Fix)

#### Test 1.1: Normal Login & Refresh
1. **Action:** Login with valid credentials
2. **Expected:** Redirected to dashboard, URL contains `?sid=<user-id>`
3. **Action:** Press F5 or Ctrl+R to refresh the browser
4. **Expected:** ✅ User remains logged in, dashboard still displayed
5. **Result:** PASS / FAIL

#### Test 1.2: Manual URL Manipulation
1. **Action:** After login, copy the URL with `?sid=` parameter
2. **Action:** Close browser tab
3. **Action:** Open new tab and paste the URL
4. **Expected:** ✅ User is automatically logged back in
5. **Result:** PASS / FAIL

#### Test 1.3: Invalid Session Token
1. **Action:** Manually change `?sid=` to an invalid UUID in URL
2. **Action:** Refresh the page
3. **Expected:** ✅ Redirected to login screen, query params cleared
4. **Result:** PASS / FAIL

#### Test 1.4: Logout Functionality
1. **Action:** Login and navigate to dashboard
2. **Action:** Click "🚪 Logout" button in sidebar
3. **Expected:** ✅ Immediately redirected to login screen
4. **Expected:** ✅ URL has no `?sid=` parameter
5. **Result:** PASS / FAIL

---

### 2. Attendance Workflow - Three States

#### Test 2.1: State 1 - Not Checked In
1. **Setup:** Ensure user has NO attendance record for today
2. **Action:** Navigate to "⏰ Attendance" tab
3. **Expected UI:**
   - ✅ Message: "ℹ️ You haven't checked in today."
   - ✅ Button visible: "🟢 Check In"
   - ❌ Button hidden: "🔴 Check Out"
   - ✅ Summary shows: "No Check-In Today"
4. **Result:** PASS / FAIL

#### Test 2.2: State 1 → State 2 Transition (Check In)
1. **Setup:** Start from State 1 (not checked in)
2. **Action:** Click "🟢 Check In" button
3. **Expected:**
   - ✅ Page automatically refreshes (st.rerun)
   - ✅ NO intermediate success message
   - ✅ Immediately shows State 2 UI
4. **Verify Database:**
   ```sql
   SELECT * FROM attendance WHERE user_id = '<your-id>' AND date = CURRENT_DATE;
   ```
   - ✅ Record exists with `check_in` timestamp
   - ✅ `check_out` is NULL
5. **Result:** PASS / FAIL

#### Test 2.3: State 2 - Active Shift
1. **Setup:** User has checked in (State 2)
2. **Expected UI:**
   - ✅ Message: "✅ You are currently Checked In (Shift active since HH:MM:SS)"
   - ✅ Metric: "Current Duration" showing live hours
   - ❌ Button hidden: "🟢 Check In"
   - ✅ Button visible: "🔴 Check Out"
   - ✅ Summary shows: "⏱️ Active Shift" with check-in time
3. **Action:** Refresh browser (F5)
4. **Expected:** ✅ Still shows State 2 (session persisted)
5. **Result:** PASS / FAIL

#### Test 2.4: State 2 → State 3 Transition (Check Out)
1. **Setup:** Start from State 2 (active shift)
2. **Action:** Click "🔴 Check Out" button
3. **Expected:**
   - ✅ Page automatically refreshes (st.rerun)
   - ✅ NO intermediate success message
   - ✅ Immediately shows State 3 UI
4. **Verify Database:**
   ```sql
   SELECT * FROM attendance WHERE user_id = '<your-id>' AND date = CURRENT_DATE;
   ```
   - ✅ `check_out` timestamp now populated
   - ✅ `regular_hours` calculated
   - ✅ `overtime_hours` calculated (if applicable)
5. **Result:** PASS / FAIL

#### Test 2.5: State 3 - Shift Completed with Payroll
1. **Setup:** User has completed shift (checked out)
2. **Expected UI:**
   - ✅ Message: "✅ Your Shift is Off"
   - ❌ Button hidden: "🟢 Check In"
   - ❌ Button hidden: "🔴 Check Out"
   - ✅ Summary shows: "✅ Shift Completed" with full details
   - ✅ Payroll section displays:
     - Regular Hours metric
     - Overtime Hours metric
     - Total Hours metric
     - **Regular Pay** (regular_hours × hourly_rate)
     - **Overtime Pay** (overtime_hours × hourly_rate × 1.5)
     - **Total Gross Pay** (sum of above)
     - Rate information caption
3. **Action:** Refresh browser
4. **Expected:** ✅ Still shows State 3 (data persists)
5. **Result:** PASS / FAIL

---

### 3. Payroll Calculation Accuracy

#### Test 3.1: Regular Hours Only (< 8 hours)
1. **Setup:** Work 6 hours (no overtime)
2. **Example:**
   - Hourly Rate: $20.00
   - Regular Hours: 6.00
   - Overtime Hours: 0.00
3. **Expected Calculation:**
   - Regular Pay: $120.00 (6 × $20)
   - Overtime Pay: $0.00
   - Total Gross Pay: $120.00
4. **Verify:** ✅ Values match expected
5. **Result:** PASS / FAIL

#### Test 3.2: With Overtime (> 8 hours)
1. **Setup:** Work 10 hours (8 regular + 2 overtime)
2. **Example:**
   - Hourly Rate: $25.00
   - Regular Hours: 8.00
   - Overtime Hours: 2.00
3. **Expected Calculation:**
   - Regular Pay: $200.00 (8 × $25)
   - Overtime Pay: $75.00 (2 × $25 × 1.5)
   - Total Gross Pay: $275.00
4. **Verify:** ✅ Values match expected
5. **Result:** PASS / FAIL

#### Test 3.3: No Hourly Rate Set
1. **Setup:** User has hourly_rate = 0 or NULL
2. **Expected:**
   - ✅ Warning displayed: "⚠️ Hourly rate not set. Please contact HR..."
   - ✅ No payroll calculations shown
3. **Result:** PASS / FAIL

#### Test 3.4: Fractional Hours Precision
1. **Setup:** Work 7.25 hours (7 hours 15 minutes)
2. **Example:**
   - Hourly Rate: $30.00
   - Regular Hours: 7.25
3. **Expected Calculation:**
   - Regular Pay: $217.50 (7.25 × $30)
4. **Verify:** ✅ Decimal precision maintained (not rounded early)
5. **Result:** PASS / FAIL

---

### 4. Edge Cases & Error Handling

#### Test 4.1: Double Check-In Prevention
1. **Setup:** User already has active shift (State 2)
2. **Action:** Try to manually trigger check-in
3. **Expected:** ✅ Check-in button not visible (state detection works)
4. **Result:** PASS / FAIL

#### Test 4.2: Check-Out Without Check-In
1. **Setup:** No attendance record for today
2. **Expected:** ✅ Check-out button not visible
3. **Result:** PASS / FAIL

#### Test 4.3: Database Transaction Integrity
1. **Action:** Perform check-in
2. **Action:** Immediately refresh before rerun completes
3. **Expected:** ✅ Data persisted (db.commit() and db.flush() working)
4. **Result:** PASS / FAIL

#### Test 4.4: Timezone Handling
1. **Setup:** Server in different timezone than user
2. **Action:** Check-in and check-out
3. **Expected:** ✅ Times displayed correctly in UTC
4. **Result:** PASS / FAIL

#### Test 4.5: Concurrent Sessions (Multiple Tabs)
1. **Action:** Open dashboard in two browser tabs
2. **Action:** Check-in from Tab 1
3. **Action:** Switch to Tab 2 and refresh
4. **Expected:** ✅ Tab 2 shows updated state (State 2)
5. **Result:** PASS / FAIL

---

## Database Verification Queries

### Check Current Attendance Status
```sql
SELECT 
    u.full_name,
    a.date,
    a.check_in,
    a.check_out,
    a.regular_hours,
    a.overtime_hours,
    a.status,
    u.hourly_rate
FROM attendance a
JOIN users u ON a.user_id = u.id
WHERE a.date = CURRENT_DATE
AND u.email = 'your.email@example.com';
```

### Verify Session Token
```sql
SELECT id, email, full_name, is_active
FROM users
WHERE id = '<session-id-from-url>';
```

### Calculate Expected Pay
```sql
SELECT 
    a.regular_hours,
    a.overtime_hours,
    u.hourly_rate,
    (a.regular_hours * u.hourly_rate) as regular_pay,
    (a.overtime_hours * u.hourly_rate * 1.5) as overtime_pay,
    (a.regular_hours * u.hourly_rate) + (a.overtime_hours * u.hourly_rate * 1.5) as total_gross_pay
FROM attendance a
JOIN users u ON a.user_id = u.id
WHERE a.date = CURRENT_DATE
AND a.check_out IS NOT NULL;
```

---

## Manual Test Setup Script

If you need to manually test different states, you can use these SQL commands:

### Reset Today's Attendance
```sql
DELETE FROM attendance 
WHERE user_id = '<your-user-id>' 
AND date = CURRENT_DATE;
```

### Create Active Shift (State 2)
```sql
INSERT INTO attendance (user_id, date, check_in, regular_hours, overtime_hours, status)
VALUES ('<your-user-id>', CURRENT_DATE, NOW(), 0, 0, 'present');
```

### Create Completed Shift (State 3)
```sql
INSERT INTO attendance (user_id, date, check_in, check_out, regular_hours, overtime_hours, status)
VALUES (
    '<your-user-id>', 
    CURRENT_DATE, 
    NOW() - INTERVAL '10 hours',
    NOW() - INTERVAL '2 hours',
    8.00, 
    2.00, 
    'present'
);
```

### Update Hourly Rate
```sql
UPDATE users 
SET hourly_rate = 25.00 
WHERE id = '<your-user-id>';
```

---

## Success Criteria

All tests should PASS for complete implementation verification:

- ✅ Session persists across browser refresh
- ✅ State transitions are immediate (st.rerun works)
- ✅ Three attendance states display correctly
- ✅ Buttons show/hide based on state
- ✅ Payroll calculations are accurate
- ✅ Decimal precision maintained
- ✅ Overtime calculated at 1.5x
- ✅ Logout clears session completely
- ✅ Database transactions are reliable
- ✅ Error handling for missing hourly rate

---

## Troubleshooting

### Issue: Session not persisting after refresh
- Check browser console for errors
- Verify `st.query_params` is supported (Streamlit >= 1.30)
- Check that `sid` parameter appears in URL after login

### Issue: UI not updating after check-in/out
- Verify `st.rerun()` is being called
- Check database transaction commits (`db.commit()`, `db.flush()`)
- Look for exceptions in terminal logs

### Issue: Payroll shows $0.00
- Verify user has `hourly_rate > 0` in database
- Check that `user_hourly_rate` is in session state
- Verify attendance record has hours calculated

### Issue: Wrong button visibility
- Check state detection logic: `is_checked_in`, `is_completed`
- Verify `is_open_shift` property works correctly
- Check database has correct `check_out` values

---

## Contact

If you encounter any issues during testing, check:
1. Terminal output for Python errors
2. Browser console for JavaScript errors
3. Database logs for transaction issues
4. `IMPLEMENTATION_SUMMARY.md` for technical details

Happy Testing! 🚀
