import { python } from '@codemirror/lang-python'
import { javascript } from '@codemirror/lang-javascript'
import { java } from '@codemirror/lang-java'
import { cpp } from '@codemirror/lang-cpp'
import { StreamLanguage } from '@codemirror/language'
import { go } from '@codemirror/legacy-modes/mode/go'

export const LANGUAGES = [
  { value: 'python', label: 'Python' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'java', label: 'Java' },
  { value: 'cpp', label: 'C++' },
  { value: 'go', label: 'Go' },
]

export function getLanguageExtension(language) {
  switch (language) {
    case 'python':
      return python()
    case 'javascript':
      return javascript()
    case 'java':
      return java()
    case 'cpp':
      return cpp()
    case 'go':
      return StreamLanguage.define(go)
    default:
      return python()
  }
}

export const SAMPLE_CODE = {
  python: `def get_average(scores):
    total = 0
    for s in scores:
        total += s
    return total / len(scores)

api_key = "sk-live-12345"

try:
    result = get_average([])
except:
    pass
`,
  javascript: `var apiKey = "sk-live-12345";

function getAverage(scores) {
  var total = 0;
  for (var i = 0; i <= scores.length; i++) {
    total += scores[i];
  }
  return total / scores.length;
}

console.log(getAverage([1, 2, 3]));
`,
  java: `public class Calculator {
    static String apiKey = "sk-live-12345";

    public int average(int[] scores) {
        int total = 0;
        for (int i = 0; i <= scores.length; i++) {
            total += scores[i];
        }
        return total / scores.length;
    }
}
`,
  cpp: `#include <iostream>
using namespace std;

int average(int scores[], int size) {
    int total = 0;
    for (int i = 0; i <= size; i++) {
        total += scores[i];
    }
    return total / size;
}

int main() {
    int scores[3] = {1, 2, 3};
    cout << average(scores, 3) << endl;
}
`,
  go: `package main

import "fmt"

func average(scores []int) int {
	total := 0
	for _, s := range scores {
		total += s
	}
	return total / len(scores)
}

func main() {
	data, err := fetchScores()
	fmt.Println(average(data))
}
`,
}
