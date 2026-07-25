# Conventional Commit Guidelines

AET uses conventional commits to keep git history clean and meaningful.

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Type

Must be one of the following:

- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation only changes
- **style**: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc)
- **refactor**: A code change that neither fixes a bug nor adds a feature
- **perf**: A code change that improves performance
- **test**: Adding missing tests or correcting existing tests
- **chore**: Changes to the build process, dependencies, or tooling
- **ci**: Changes to CI/CD configuration or scripts

## Scope

The scope specifies what part of the codebase is affected:

- `drawing-engine` - Drawing engine feature
- `asset-engine` - Asset engine feature
- `validation-engine` - Validation engine feature
- `repository-foundation` - Repository foundation feature
- `core` - Core functionality
- etc.

## Subject

The subject line should:
- Use the imperative, present tense: "change" not "changed" or "changes"
- Don't capitalize first letter
- No period (.) at the end
- Limit to 50 characters

## Body

Optional but recommended for non-trivial commits. Explain:
- What the change does
- Why the change is needed
- How it affects the system

## Footer

Optional. Reference issues:
```
Fixes #123
Closes #456
Related-To #789
```

## Examples

### Feature
```
feat(drawing-engine): implement DWG parser for line entities

Add support for parsing LINE entities from DWG files.
Includes coordinate extraction and layer mapping.

Fixes #42
```

### Bug Fix
```
fix(validation-engine): correct arc radius calculation

The radius calculation was using incorrect formula for elliptical arcs.
Updated to use proper geometric calculation.

Fixes #89
```

### Documentation
```
docs(sds): update drawing-engine specification

Added clarification on DWG entity priority handling
and updated data structure diagrams.
```

### Test
```
test(validation): add comprehensive test suite for geometry validation

Add 47 new test cases covering:
- Line-to-line intersection
- Arc-to-arc intersection  
- Polygon containment
- Edge cases with floating point precision

Relates-To #100
```
