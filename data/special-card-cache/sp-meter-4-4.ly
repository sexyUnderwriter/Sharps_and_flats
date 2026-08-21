\version "2.24.0"
#(set-global-staff-size 64)
\paper {
    #(set-paper-size "a6")
    top-margin = 0
    bottom-margin = 0
    left-margin = 0
    right-margin = 0
    indent = 0
    tagline = ##f
    print-page-number = ##f
}
\score {
    \new Staff \with {
        \remove "Clef_engraver"
        \remove "Staff_symbol_engraver"
        \remove "Bar_engraver"
    } {
        \numericTimeSignature
        \time 4/4
        s1
    }
}
