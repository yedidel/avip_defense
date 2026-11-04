--------------------------- MODULE DecisionBinding ---------------------------
(***************************************************************************)
(* Bounded model of decision-basis binding in an AP2-style human-present  *)
(* purchase (binding/ in this repository).                                *)
(*                                                                         *)
(* Property (stated without reference to the mechanism):                  *)
(*   a statement about an offer o can influence which offer is signed only *)
(*   if its speaker is responsible for o (sells o), or the agent received  *)
(*   it together with its speaker (annotated provenance).                  *)
(*                                                                         *)
(* The agent is modelled as worst case: its choice may be influenced by   *)
(* ANY subset of the statements in its context. Merchant-controlled text   *)
(* reaches the agent on two channels: the search response and the         *)
(* checkout response (which repeats the chosen offer's label; F1 row 4).  *)
(* After the checkout response the agent may still re-select (ADK         *)
(* sub-agent transfer), so text on that channel can change the choice.    *)
(*                                                                         *)
(* Universe (bounded): sellers A, B; offers o1 (A, title t1), o2 (B, t2),  *)
(* o3 (A, t2): o3 is A's copy of B's title (identity case, F3).            *)
(* A statement is [speaker |-> offer, about |-> title]; every possible     *)
(* statement is in the merchant text (the adversary writes anything).     *)
(***************************************************************************)
EXTENDS FiniteSets, TLC

CONSTANTS
    WrapSearch,      \* W captures and filters the search response
    WrapCheckout,    \* W also filters the checkout response (F1, channel 4)
    Policy,          \* "NONE", "STRIP" or "ANNOTATE"
    Expansion,       \* target expansion over equal titles (identity rule)
    PerfectA         \* TRUE: attributor finds every statement; FALSE: it may miss any

Offers  == {"o1", "o2", "o3"}
Titles  == {"t1", "t2"}
seller  == [o \in Offers |-> IF o = "o2" THEN "B" ELSE "A"]
title   == [o \in Offers |-> IF o = "o1" THEN "t1" ELSE "t2"]
Stmts   == [speaker : Offers, about : Titles]
None    == "none"

Responsible(sp, o) == seller[sp] = seller[o]
TrueReferents(s)   == {o \in Offers : title[o] = s.about}       \* what the text is really about

\* What the mechanism resolves a statement to.
MechReferents(s) ==
    IF Expansion THEN TrueReferents(s)
    ELSE LET own == {o \in TrueReferents(s) : seller[o] = seller[s.speaker]}
         IN IF own # {} THEN own ELSE TrueReferents(s)   \* resolver prefers the speaker's own copy

NonAuth(s) == \E o \in MechReferents(s) : ~Responsible(s.speaker, o)

VARIABLES missed, context, chosen, influence, signed, pc
vars == << missed, context, chosen, influence, signed, pc >>

\* What one channel delivers, given the mechanism on that channel.
Deliver(S, wrapped) ==
    IF ~wrapped \/ Policy = "NONE"
    THEN {[s |-> x, annotated |-> FALSE] : x \in S}
    ELSE LET caught == {x \in S : x \notin missed /\ NonAuth(x)}
         IN  IF Policy = "STRIP"
             THEN {[s |-> x, annotated |-> FALSE] : x \in S \ caught}
             ELSE {[s |-> x, annotated |-> (x \in caught)] : x \in S}

Init ==
    /\ missed \in (IF PerfectA THEN {{}} ELSE SUBSET Stmts)
    /\ context = {}
    /\ chosen = None
    /\ influence = {}
    /\ signed = None
    /\ pc = "search"

Search ==
    /\ pc = "search"
    /\ context' = Deliver(Stmts, WrapSearch)
    /\ pc' = "choose"
    /\ UNCHANGED << missed, chosen, influence, signed >>

Choose ==
    /\ pc \in {"choose", "rechoose"}
    /\ \E o \in Offers, I \in SUBSET context :
          /\ chosen' = o
          /\ influence' = I
    /\ pc' = IF pc = "choose" THEN "checkout" ELSE "sign"
    /\ UNCHANGED << missed, context, signed >>

\* Checkout response: the chosen offer's label again (statements spoken by the chosen offer).
Checkout ==
    /\ pc = "checkout"
    /\ context' = context \cup Deliver({x \in Stmts : x.speaker = chosen}, WrapCheckout)
    /\ pc' \in {"rechoose", "sign"}
    /\ UNCHANGED << missed, chosen, influence, signed >>

Sign ==
    /\ pc = "sign"
    /\ signed' = chosen
    /\ pc' = "done"
    /\ UNCHANGED << missed, context, chosen, influence >>

Done == pc = "done" /\ UNCHANGED vars

Next == Search \/ Choose \/ Checkout \/ Sign \/ Done
Spec == Init /\ [][Next]_vars

(* The property, mechanism-independent. *)
BasisBound ==
    signed # None =>
      \A d \in influence :
         d.annotated \/ \A o \in TrueReferents(d.s) : Responsible(d.s.speaker, o)

(* With an imperfect attributor: every violation is a missed attribution. *)
ViolationIsMiss ==
    (signed # None /\ ~BasisBound) =>
      \E d \in influence : d.s \in missed /\ ~d.annotated
==============================================================================
