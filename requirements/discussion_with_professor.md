
NV
Noah Velez
Sep 28 11:44am
| Last reply Sep 29 10:59am

Both 1 and 2 complement each other because they point to the same underlying problem: alignment.

1. Would you have held your ground?
If a user or stakeholder tells me I am wrong, how do I know that I am actually right? Was there a misunderstanding during requirements gathering? Does the stakeholder fully understand the technical implications of the requirements they provided? Confidence on either side does not necessarily mean the underlying interpretation is correct.

2. Fluent and wrong, in the wild.
The same problem exists with coding agents. How do I know the agent actually understood the requirements rather than producing a convincing implementation of the wrong interpretation?

Both humans and AI generalize from incomplete information. A stakeholder may understand the business problem but leave out technical details needed to implement it correctly. Likewise, an AI agent may understand the request at a high level but lack important context about the data model, system architecture, or business rules. In either case, the result can be internally logical and confidently explained while still being wrong.

To me, that makes verification less about asking, "Who is right?" and more about checking whether the requirement, interpretation, and implementation are actually aligned.


Hide 3 Replies
Reply
Mark as Unread
Paulo Cavallo
AuthorTeacher
Sep 28 2:10pm

Noah, great post. I taught verification as catching a wrong answer. You've pointed out that in real work, the wrong answer usually isn't wrong in isolation. It's a correct implementation of a wrong interpretation, and everything downstream of the misunderstanding is internally consistent. That's why it survives review... the code does exactly what somebody thought was being asked.

Your three-way alignment check, requirement against interpretation against implementation, is a better test than "is this right," because it tells you WHERE the break is. A stakeholder who knows the business but not the data model, and an agent that has the request but not the schema, fail the same way and for the same reason.

And it explains something I only asserted in class. I said the judge should be a different model, one that didn't write the code. Your framing says why that works... the judge doesn't hold the first one's interpretation, so it reads what's actually there rather than what somebody meant. Same reason a second pair of human eyes catches things.

One thing to be careful with, since you're treating both sides as symmetric. They're not, in one respect... you can ask the stakeholder what they meant. You cannot ask the agent, because whatever it tells you comes from the same interpretation that produced the code. Its explanation of itself is not independent evidence. That's why testing beats asking.

Now the missing piece. You answered one and two and skipped three.

Your framing suggests you're building something with real requirements behind it, so: where's the one decision your agent makes? Not which tool it calls, but the point where it weighs something and could reasonably go either way.

Worth posting, because the alignment question you just described is exactly what you'll have to answer about your own project.

Reply
Mark as Unread
NV
Noah Velez
Sep 28 7:06pm

For my mini-project, I’m building a chess coach, and I think the one real decision is what the player should learn from a position or mistake.

The deterministic parts can come from an engine: evaluation changes, best moves, tactical opportunities, and whether a move was a blunder.

But knowing that I lost 2.5 points of evaluation does not necessarily tell me what the coaching takeaway should be.

The model has to look at the position, the mistake, and the surrounding game and decide whether the useful lesson is something like calculation discipline, piece safety, an opening principle, or recognizing a tactical motif.

That decision could reasonably go multiple ways even when the underlying engine analysis is identical.

The agent’s job would be to choose the most useful coaching intervention and explain why, while the engine provides the objective chess evidence underneath it.

Reply
Mark as Unread
Paulo Cavallo
AuthorTeacher
Sep 29 10:59am

@Noah Velez, this is a really clean split, and the line I'd want everyone to pay attention to: "that decision could reasonably go multiple ways even when the underlying engine analysis is identical."

That's the test. Same inputs, defensible different answers, no rule settles it. The engine tells you the move lost 2.5 points, which is a fact. What the player should take away from it is a coaching judgment, and two good coaches would say different things.

I like that the engine does the objective work for free. Stockfish will give you evaluation swings and best moves all day at no cost and no latency, so every token you spend goes on the part that actually needs a model. That's the right place to spend it.

One thing I'd think about... the best takeaway probably depends on who's playing. "You hung a piece because you didn't check what was attacked" is the right lesson for one player and patronising to another who knows that perfectly well and miscalculated a line. Same position, same blunder, different useful advice.

You don't have to solve that. But if you give the agent even a little context about the player, their rating, or the last few mistakes they made, the decision gets more interesting and more clearly a judgment.

And your evaluation is sitting right there. Take five or six positions where you already know what you'd tell the player, including one or two you'd have to think about. See where it agrees with you. Where it doesn't, that's either your prompt or your own coaching instinct, and both are worth knowing.

Outstanding work! Look forward to seeing it live during your presentation.