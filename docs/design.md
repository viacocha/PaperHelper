# PaperHelper Design Snapshot

## V1 scope

- local web app
- `.docx` upload only
- standards for selected knowledge areas and performance domains
- score + issues + paragraph suggestions + suggestion DOCX output

## Backend flow

1. upload essay
2. parse DOCX paragraphs
3. match standard by selected id or keyword confidence
4. run generic + topic-specific checks
5. build review result
6. generate `同名+修改建议.docx`

## Frontend flow

1. load standards
2. upload essay and optional standard
3. show total score, issue list, paragraph feedback
4. download generated report
