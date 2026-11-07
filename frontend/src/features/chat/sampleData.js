// FAKE data so the layout can be judged before anything is wired to the backend. Same shapes the API will return
// (conversation rows, messages with `citations`). Deleted when the chat is connected.

export const SAMPLE_MESSAGES = [
  { id: 1, role: 'user', content: 'How many vacation days do employees get, and can unused days be carried over?' },
  {
    id: 2,
    role: 'assistant',
    content:
      'Full-time employees get 25 vacation days per year [1]. Unused days can be carried over until the end of March of the following year, after which they expire [2].',
    citations: [
      {
        n: 1,
        filename: 'leave_policy.pdf',
        page: 3,
        snippet:
          'Employees are entitled to 25 vacation days per calendar year, prorated for part-time staff and for employees who join during the year. Requests are submitted through the HR portal at least two weeks ahead.',
      },
      {
        n: 2,
        filename: 'employee_handbook.docx',
        section: 'Time off',
        snippet:
          'Vacation days that are not used by 31 December may be carried over to the next year. Carried-over days must be taken by 31 March; after that date they expire without compensation.',
      },
    ],
  },
  { id: 3, role: 'user', content: 'What is the parental leave policy?' },
  {
    id: 4,
    role: 'assistant',
    content: "I couldn't find anything about parental leave in your documents.",
    citations: [],
  },
]
