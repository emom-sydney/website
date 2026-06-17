**** Tips & Tricks for the human in charge of the database

Keeping a note of manual operations here for reference & fallback in the event of losing the ability to generate this SQL automatically.

To manually update performers from 'requested' to 'selected' status for a given event.
First, a sanity check. Supply a value for event_id and and an array referring to the id of the artist's record in the `profile_submission_drafts` table:

```sql
SELECT
  psd.id AS draft_id,
  psd.profile_id,
  psd.display_name,
  rd.id AS requested_date_id,
  rd.status AS request_status
FROM profile_submission_drafts psd
LEFT JOIN requested_dates rd
  ON rd.draft_id = psd.id
 AND rd.event_id = 14
WHERE psd.id = ANY (ARRAY[3, 41, 35, 36, 32, 8]::bigint[])
ORDER BY array_position(ARRAY[3, 41, 35, 36, 32, 8]::bigint[], psd.id);
```

That query should return a result for every id, so you can proceed to update the tables accordingly. (If it returns NULL rows, well we have a problem)

```sql
BEGIN;

WITH selected_drafts AS (
  SELECT unnest(ARRAY[3, 41, 35, 36, 32, 8]::bigint[]) AS draft_id
),
request_rows AS (
  SELECT
    rd.id AS requested_date_id,
    rd.event_id,
    psd.profile_id
  FROM selected_drafts sd
  JOIN profile_submission_drafts psd
    ON psd.id = sd.draft_id
  JOIN requested_dates rd
    ON rd.draft_id = psd.id
   AND rd.event_id = 14
  WHERE psd.profile_id IS NOT NULL
)
INSERT INTO event_performer_selections (
  event_id,
  profile_id,
  requested_date_id,
  status,
  selected_at
)
SELECT
  event_id,
  profile_id,
  requested_date_id,
  'selected',
  now()
FROM request_rows
ON CONFLICT (event_id, profile_id)
DO UPDATE SET
  requested_date_id = EXCLUDED.requested_date_id,
  status = 'selected',
  selected_at = now();

WITH selected_drafts AS (
  SELECT unnest(ARRAY[3, 41, 35, 36, 32, 8]::bigint[]) AS draft_id
)
UPDATE requested_dates rd
SET
  status = 'selected',
  selected_at = now()
FROM selected_drafts sd
WHERE rd.draft_id = sd.draft_id
  AND rd.event_id = 14;

COMMIT;
```

To update the artist submissions that *weren't* selected for event id 14, we run this preflight check:

```sql
SELECT
  rd.id AS requested_date_id,
  rd.status AS current_status,
  psd.id AS draft_id,
  psd.profile_id,
  psd.display_name,
  psd.email
FROM requested_dates rd
JOIN profile_submission_drafts psd
  ON psd.id = rd.draft_id
WHERE rd.event_id = 14
  AND rd.status IN ('requested', 'availability_confirmed')
  AND NOT EXISTS (
    SELECT 1
    FROM event_performer_selections eps
    WHERE eps.event_id = rd.event_id
      AND eps.requested_date_id = rd.id
      AND eps.status IN ('selected', 'standby', 'reserve')
  )
ORDER BY lower(psd.display_name), rd.id;
```

and then assuming no NULL rows returned we can run:

```sql
SELECT
  rd.id AS requested_date_id,
  rd.status AS current_status,
  psd.id AS draft_id,
  psd.profile_id,
  psd.display_name,
  psd.email
FROM requested_dates rd
JOIN profile_submission_drafts psd
  ON psd.id = rd.draft_id
WHERE rd.event_id = 14
  AND rd.status IN ('requested', 'availability_confirmed')
  AND NOT EXISTS (
    SELECT 1
    FROM event_performer_selections eps
    WHERE eps.event_id = rd.event_id
      AND eps.requested_date_id = rd.id
      AND eps.status IN ('selected', 'standby', 'reserve')
  )
ORDER BY lower(psd.display_name), rd.id;
```

To generate a list of people who weren't selected for an event, in a format that can be copy/pasted into an email client so you can send them the bad news (change to `AND rd.status = 'selected'` for the good news recipients )

```sql
SELECT string_agg(
  psd.display_name || ' <' || psd.email || '>',
  ', ' ORDER BY lower(psd.display_name), psd.email
) AS mail_recipients
FROM requested_dates rd
JOIN profile_submission_drafts psd
  ON psd.id = rd.draft_id
WHERE rd.event_id = 14
  AND rd.status = 'selected'
  AND psd.email IS NOT NULL
  AND btrim(psd.email) <> '';
```

