# GitHub Release Manual

Follow these steps to create a new release for OLED Customizer:

## 1. Build the Project

Run the build script to generate the executable and the browser extension:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

This will create:

- `dist/OLED-Customizer.exe`
- `dist/OLED-Customizer-Extension.crx`

## 2. Commit and Push

Ensure the version in `version.py` is updated, then commit:

```bash
git add .
git commit -m "vX.X.X: [Summary of changes]"
git push
```

## 3. Create the Release

Use the GitHub CLI (`gh`) to create the release and upload both assets:

```bash
gh release create vX.X.X dist/OLED-Customizer.exe dist/OLED-Customizer-Extension.crx --title "vX.X.X - [Title]" --notes "[Release Notes]"
```

## 4. Post-Release

Copy the new executable to the root folder (as per workspace rules):

```powershell
copy dist\OLED-Customizer.exe OLED_Customizer.exe
```
