// How Clerk's forms look. Clerk draws the fields and handles every step (codes, errors, social logins); this file
// only styles it. `elements` takes Tailwind classes.
//
// Tailwind's utilities can only beat Clerk's own CSS because Clerk is put in a CSS layer named "clerk"
// (see cssLayerName in ClerkWithRouter.jsx and the @layer line at the top of index.css).
//
// The motion lives in index.css (.auth-form-in staggers the pieces, .auth-shake shakes an error) and in the classes
// below: hover lift, press-down on click (the ripple itself is added by AuthLayout), a glowing ring on focus.
// `motion-safe:` means "only for people who did not ask their system for less motion".

// Colours for everything Clerk draws, including the account menu in the top bar (used by ClerkWithRouter too).
export const clerkVariables = {
  colorPrimary: '#0f6b5c', // brand-700
  colorText: '#1a2321', // ink
  colorTextSecondary: '#57534e', // stone-600 (4.5:1 or better on white and on paper)
  colorBackground: '#ffffff',
  colorInputBackground: '#fafaf9', // stone-50
  colorInputText: '#1a2321',
  borderRadius: '0.75rem',
  fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  fontSize: '0.9375rem',
}

// The same for dark mode (Graphite, see .dark in index.css). colorNeutral drives Clerk's own borders and shades.
export const clerkDarkVariables = {
  ...clerkVariables,
  colorText: '#e5e5e5',
  colorTextSecondary: '#a3a3a3',
  colorBackground: '#1c1c1c',
  colorInputBackground: '#181818',
  colorInputText: '#e5e5e5',
  colorNeutral: '#ffffff',
}

// The form's appearance for the current theme.
export function authAppearanceFor(theme) {
  return theme === 'dark' ? { ...authAppearance, variables: clerkDarkVariables } : authAppearance
}

export const authAppearance = {
  layout: {
    socialButtonsVariant: 'iconButton', // a row of small square icon buttons instead of full-width ones
    socialButtonsPlacement: 'bottom',
    logoPlacement: 'none', // our card already shows the name
    unsafe_disableDevelopmentModeWarnings: true, // hides Clerk's "Development mode" ribbon while developing
  },
  variables: clerkVariables,
  elements: {
    // remove Clerk's own card: our white card is the container
    rootBox: 'w-full',
    cardBox: 'w-full overflow-visible border-0 shadow-none', // Clerk's own cardBox clips (overflow hidden) the first letter of the title
    card: 'w-full gap-6 bg-transparent p-0 shadow-none',

    header: 'items-start overflow-visible text-left',
    headerTitle: 'overflow-visible text-left font-display text-4xl font-semibold tracking-tight text-ink',
    headerSubtitle: 'text-left text-stone-600',

    formFieldLabel: 'font-semibold text-stone-700',
    formFieldInput:
      'h-11 rounded-xl border border-stone-200 bg-stone-50 shadow-none transition duration-200 focus:border-brand-600 focus:bg-surface focus:ring-4 focus:ring-brand-100',
    formFieldAction: 'font-semibold text-brand-700 hover:text-brand-800',
    formFieldInputShowPasswordButton: 'transition-colors hover:text-brand-700',
    formFieldErrorText: 'auth-shake',

    formButtonPrimary:
      'relative h-11 overflow-hidden rounded-xl bg-brand-700 text-sm font-semibold normal-case shadow-lg shadow-brand-900/25 transition duration-200 hover:bg-brand-800 hover:shadow-xl hover:shadow-brand-900/30 motion-safe:hover:-translate-y-0.5 motion-safe:active:translate-y-0 motion-safe:active:scale-[0.98]',
    socialButtonsIconButton:
      'relative h-11 overflow-hidden rounded-xl border border-stone-200 bg-surface shadow-none transition duration-200 hover:border-brand-300 hover:bg-brand-50 motion-safe:hover:-translate-y-0.5 motion-safe:active:scale-[0.98]',
    dividerLine: 'bg-stone-200',
    dividerText: 'text-stone-500',

    // Clerk's footer ("Secured by Clerk", and the sign-up link on phones) comes with a grey background: remove it
    footer: 'bg-transparent bg-none shadow-none',
    footerPages: 'bg-transparent',

    // "Don't have an account? Sign up": on a desktop the panel button does this job, on a phone this link stays
    footerAction: 'md:hidden',
    footerActionLink: 'font-semibold text-brand-700 transition-colors hover:text-brand-800',
  },
}
