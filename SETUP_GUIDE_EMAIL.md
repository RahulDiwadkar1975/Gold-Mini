# Step-by-Step Setup — Daily Gold Signal to Email

This guide takes you from zero to a working system that emails you the Gold Mini
Total Score, Confidence and Signal every weekday at **09:00 IST**, and flags
whenever the signal changes. It runs on GitHub's free servers, so **your computer
does not need to be on.**

**Time needed:** ~15–20 minutes. No coding required — just clicking and pasting.

**You need:** a Gmail account and a (free) GitHub account. That's it.

---

## Part 1 — Download the three files

From this chat, download the files I shared:
- `gold_signal_email.py`
- `requirements.txt`
- `daily_email.yml`

Keep them somewhere you can find them (e.g. your Downloads folder).

---

## Part 2 — Create a Gmail App Password (one time)

Your normal Gmail password won't work from a script — Google needs a special
"App Password." Here's how:

1. Go to **myaccount.google.com** and sign in.
2. Open **Security** (left menu).
3. Turn on **2-Step Verification** if it isn't already (this is required before
   App Passwords appear). Follow Google's prompts.
4. Now go to **myaccount.google.com/apppasswords** (or Security → App passwords).
5. Type a name like **Gold Signal** and click **Create**.
6. Google shows a **16-character code** (like `abcd efgh ijkl mnop`). **Copy it**
   and remove the spaces → `abcdefghijklmnop`. This is your **EMAIL_PASS**.

Keep this code handy for Part 5. (You can always delete it later in the same place.)

---

## Part 3 — Create your GitHub repository

1. Go to **github.com** and sign up / log in (free).
2. Click the **+** at the top-right → **New repository**.
3. **Repository name:** `gold-signal` (any name is fine).
4. Choose **Private**.
5. Tick **Add a README file**.
6. Click **Create repository**.

You now have an (almost) empty project to put the files in.

---

## Part 4 — Add the three files

**The two code files:**
1. In your repo, click **Add file → Upload files**.
2. Drag `gold_signal_email.py` and `requirements.txt` into the box.
3. Click **Commit changes**.

**The schedule file (needs a special folder):**
4. Click **Add file → Create new file**.
5. In the filename box at the top, type exactly:
   ```
   .github/workflows/daily_email.yml
   ```
   As you type each `/`, GitHub automatically creates the folder. 
6. Open your downloaded `daily_email.yml`, copy everything, and paste it into the
   big editing box.
7. Click **Commit changes**.

Your repo should now contain: `gold_signal_email.py`, `requirements.txt`, a
`README.md`, and `.github/workflows/daily_email.yml`.

---

## Part 5 — Add your secrets (email login)

These keep your password safe — they're encrypted and never shown again.

1. In your repo, click **Settings** (top menu).
2. Left menu → **Secrets and variables → Actions**.
3. Click **New repository secret** and add each of these (one at a time):

   | Name | Value |
   |---|---|
   | `EMAIL_FROM` | your Gmail address, e.g. `you@gmail.com` |
   | `EMAIL_PASS` | the 16-character App Password (no spaces) |
   | `EMAIL_TO` | where to send it (your email, or any address) |

   For each: type the **Name**, paste the **Secret**, click **Add secret**.

---

## Part 6 — Allow the workflow to save its memory

This lets the system remember yesterday's signal so it can detect changes.

1. Still in **Settings**, left menu → **Actions → General**.
2. Scroll to **Workflow permissions**.
3. Select **Read and write permissions**.
4. Click **Save**.

---

## Part 7 — Test it now

1. Click the **Actions** tab (top menu).
2. On the left, click **Gold Mini Daily Signal (Email)**.
3. Click **Run workflow** (right side) → then the green **Run workflow** button.
4. Wait ~1 minute, then refresh. A yellow dot means running, green tick means done.
5. **Check your email inbox** (and spam folder) — you should have a message with a
   subject like `Gold Signal: BUY PUT (High)`.

If it didn't arrive, click the run → the **Run signal** step to see the logs. The
script prints the full message and any error there. See Troubleshooting below.

---

## You're done! What happens now

- Every **weekday at 09:00 IST**, you'll automatically get the email — no action
  needed, computer off or on.
- The **subject line shows the signal**, so you can read it from the notification.
- When the signal **changes** from the day before, the subject becomes
  `[SIGNAL CHANGED] ...` and the body shows the old → new signal.

---

## Updating the manual inputs

Four inputs (OI, PCR, Max Pain, FII) and central-bank buying have no free data
source, so they're numbers near the top of the script that you update when you
check your MCX option chain:

1. In your repo, click `gold_signal_email.py`.
2. Click the **pencil icon** (Edit) at the top-right of the file.
3. Change the numbers in the `CONFIG` section, for example:
   ```
   OI_TREND = -15     # strong short build-up
   PCR      = -10     # bearish
   ```
4. Click **Commit changes**.

Leave them at `0` and the score simply runs on the ~11 automatic inputs.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No email arrived | Check spam/junk first. Then check the run logs (Actions → the run → Run signal). |
| Log says "Username and Password not accepted" | Your App Password is wrong, has spaces, or 2-Step Verification isn't on. Regenerate it (Part 2). |
| Some inputs show "data err" | A free data source hiccupped that day — that input scores 0, the rest still works. Usually fixes itself next run. |
| Log shows a git push / state error | You missed Part 6 — set Workflow permissions to "Read and write". |
| "SIGNAL CHANGED" never appears | First run has nothing to compare to; it works from the second run on (needs Part 6). |
| Email arrives but time is off | GitHub cron can run a few minutes late — normal. |

---

## Optional tweaks

- **Run more often** (finer signal-change alerts): edit `.github/workflows/daily_email.yml`
  and change the cron line, e.g. `'0 4-16 * * 1-5'` runs hourly during the day.
- **Not using Gmail?** Add two more secrets: `SMTP_HOST` and `SMTP_PORT` for your
  provider (Outlook: `smtp-mail.outlook.com` / `587`). The script reads them
  automatically.
- **Change recipients:** edit the `EMAIL_TO` secret (you can send to multiple by
  using a comma-separated list as the value).

---

## Honest reminders

- Technicals run on **global gold (COMEX) as a proxy** for MCX Gold Mini; USD/INR
  is scored separately. Direction matches, but it isn't the exact MCX contract.
- IV uses the **GVZ gold-volatility index** as a proxy.
- A fully-live score (including the four option-chain inputs) needs a **broker API**
  — share one and it can be wired in.
- This is **decision-support, not financial advice.** Size and manage your own risk,
  and log the daily signal so you can judge whether it actually works for you.
