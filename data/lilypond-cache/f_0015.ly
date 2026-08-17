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
  line-width = 90\mm
}

\layout {
  ragged-right = ##f
  \context {
    \Score
    \omit BarNumber
    \override SpacingSpanner.base-shortest-duration = #(ly:make-moment 1/16)
    \override SpacingSpanner.common-shortest-duration = #(ly:make-moment 1/16)
    \override SpacingSpanner.strict-note-spacing = ##t
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
    s4 bes'8 a'8 s2
  }
}
