import { describe, expect, it } from 'vitest'
import { LANGUAGES, SAMPLE_CODE, getLanguageExtension } from './languages'

// Must stay in sync with SUPPORTED_LANGUAGES in app.py.
const BACKEND_LANGUAGES = ['cpp', 'go', 'java', 'javascript', 'python']

describe('languages', () => {
  it('offers exactly the languages the backend supports', () => {
    expect(LANGUAGES.map((l) => l.value).sort()).toEqual(BACKEND_LANGUAGES)
  })

  it('has non-empty sample code for every language', () => {
    for (const { value } of LANGUAGES) {
      expect(SAMPLE_CODE[value]?.trim().length).toBeGreaterThan(0)
    }
  })

  it('returns an editor extension for every language and falls back for unknown ones', () => {
    for (const { value } of LANGUAGES) {
      expect(getLanguageExtension(value)).toBeTruthy()
    }
    expect(getLanguageExtension('cobol')).toBeTruthy()
  })
})
