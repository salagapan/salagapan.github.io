# sankaralagapan.com

Personal academic website of Sankar Alagapan, built with [al-folio](https://github.com/alshedivat/al-folio) (Jekyll) and deployed to GitHub Pages.

## Where things live

| What | File |
| --- | --- |
| Home page bio, address | `_pages/about.md` |
| Research summary | `_pages/research.md` |
| Lab members | `_pages/lab.md` |
| Publications (journal, conference, preprints) | `_bibliography/papers.bib` |
| Patents, abstracts, posters, other writing | `_bibliography/other.bib` |
| CV page content | `_data/cv.yml` (PDF: `assets/pdf/Alagapan_CV.pdf`) |
| News items | `_news/*.md` (one file per item) |
| Social links | `_data/socials.yml` |
| Site settings | `_config.yml` |
| Profile photo | `assets/img/prof_pic.jpg` |

### Publication options (bib fields)

- `selected = {true}` shows the paper on the home page.
- `abbr = {...}` sets the venue badge.
- `html`, `pdf`, `code`, `arxiv`, `doi` add buttons; a `doi` also enables Altmetric/Dimensions badges.
- `*` after an author's last name marks equal contribution.

## Deploying

Every push to `main` runs `.github/workflows/deploy.yml`, which builds the site and pushes it to the `gh-pages` branch.
In **Settings → Pages**, the source must be **Deploy from a branch → `gh-pages` / root**.

## Local preview (optional)

```bash
bundle install && npm ci
bundle exec jekyll serve   # http://localhost:4000
```
