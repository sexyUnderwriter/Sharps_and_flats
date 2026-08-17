\version "2.24.0"
#(set-global-staff-size 200)

\paper {
  #(set-paper-size "a6")
  top-margin = 0
  bottom-margin = 0
  left-margin = 0
  right-margin = 0
  indent = 0
  tagline = ##f
  print-page-number = ##f
  line-width = 100\mm
}

\layout {
  ragged-right = ##f
  \context {
    \Score
    \omit BarNumber
    \override SpacingSpanner.uniform-stretching = ##t
  }
  \context {
    \Staff
    \omit Clef
    \omit TimeSignature
    \omit KeySignature
    \omit BarLine
  }
}

\score {
  \new Staff \with {
    \omit Clef
    \omit TimeSignature
    \omit KeySignature
    \omit BarLine
  } {
    \time 4/4
    s4 f'16 e'16 f'16 g'16 s2
  }
}
