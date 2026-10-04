What Counts as an Agent
BUAN 6V99 — Agentic AI & Process Automation Companion to the Mini-Project brief. Read both.
Posted Oct 1, 2026
Why this exists
You build the mini-project between Monday and Oct 12, so I have been rereading the brief to check that it
says what I mean. It says "one agent" and "not just a single prompt to a chatbot", and that leaves more room
than I intended. We do talk in depth about it next week, but I wanted to get this in front of you sooner.
This fills the gap. Class 6 on Monday builds a real agent line by line, but you start yours the day after, and I
would rather you began from the right idea than discovered on Oct 10 that you had built something else.
The one test
Does code that you wrote make an API call to a language model?
If no, it is not a mini-project for this course, whatever else it is.
That sounds blunt, so here is the reasoning. The thing being graded is whether you can direct AI tools to build
something and then explain how it works. If the reasoning happens inside a product somebody else built,
there is nothing of yours to explain. You configured a tool. That is a useful skill and it is not this assignment.
Three things that look like agents and are not
1. An agent you configured on somebody else's platform
This includes a custom GPT, a Claude Project, Copilot and GitHub agents or sub-agents, a Zapier or Make
automation with an AI step, and anything else where you filled in a form or wrote a system prompt in a web
interface and the platform ran the loop for you.
These are real agents. They are just not your agent. The loop belongs to GitHub or OpenAI or Zapier. You
chose settings.
The giveaway: if your repository has no file in it that imports an AI library and sends a request, there is no
agent in your repository.
2. A single prompt to a chatbot
You paste something into Claude, it gives you an answer, you copy the answer out. Even if the prompt is long
and clever, nothing is looping and nothing is deciding. One question, one answer.
3. A script with AI sprinkled on it
This one is the subtle one and it is where most people land. Your code reads a file, calls an LLM once to
summarise it, writes the result out. That is a script that happens to use an API. It is closer than the other two
MiniProject_WhatCountsAsAnAgent.md 2026-10-01
1 / 4
and it is still not an agent, because the path never changed based on what the model found.
Script or agent: the actual difference
Forget the word "agent" for a second and ask one question about your idea:
Can you write down every step, in order, before you run it?
If yes, write a script. Seriously. It will be faster, cheaper, more reliable and easier to explain. "Read these files,
extract these fields, write a CSV" is a script. Using an agent for it is worse engineering, not better.
You need an agent when the next step depends on what the last step found, and you do not know in
advance what it will find.
A worked contrast with the same subject matter:
Script. "Read my 40 meeting notes, pull out every line starting with TODO, write them to a file." You
know the steps. You know how many there are. Nothing surprises you.
Agent. "Read my 40 meeting notes and tell me which commitments I am at risk of missing." Now the
thing has to read, notice that one note mentions a deadline, go look at my calendar to see what else is
that week, decide that matters, and keep going. Which tools it calls, and how many times, depends
on what it reads. You cannot draw that flowchart in advance because the model draws it while it runs.
That is the whole distinction. A script follows a path you chose. An agent chooses the path while it is running.
What the loop actually looks like
It is smaller than you think. Roughly ninety lines of Python, and we read all of it in Class 6.
conversation = [the user's question]
repeat up to N times:
 reply = send conversation to the model # an API call. this costs
money.
 if reply starts with "FINAL:":
 return the answer # the model says it is done
 else:
 tool, args = parse the tool call out of reply
 result = run that tool myself # ordinary Python, my code
 add result to conversation # feed it back
Four moving parts: a loop, an API call, a parser, and some functions. There is no framework. You do not need
LangChain, LangGraph or CrewAI for a mini-project, and I would rather you did not use one, because the point
is that you can explain what happens.
The cap on the loop matters. Every time round is a paid API call, so an agent with a bug and no limit converts
your money into nothing. Set one.
MiniProject_WhatCountsAsAnAgent.md 2026-10-01
2 / 4
Where the judgment lives
This is the design decision that separates a real agent from a roundabout script, and it is the one I see people
get wrong.
Your tools return facts. Your agent makes the call.
A tool should do work with one right answer: read a file, query an API, check a value against a threshold,
compute an average. It hands back what it found and says nothing about what it means.
The interpretation stays with the model. Which thing matters most, how serious it is, what to do about it,
whether something is worth flagging.
If you write a tool called decide_what_to_do() and the model's only job is to repeat its output, you have
built a script with extra steps and a bigger bill. I built exactly that mistake into the Class 6 project on purpose
so you can see what it looks like from the inside.
Check your idea before you build it
Five questions. If you cannot answer yes to all five, change the idea, not the code.
1. Is there a real annoyance behind it? Something you actually do repeatedly and dislike. Not a demo
topic.
2. Does the path vary? Does what it does next genuinely depend on what it just found out? If the
sequence is always the same, it is a script.
3. Is there judgment in it? Something a threshold or an if-statement could not capture.
4. Will my own code call an LLM API? Not a platform. Mine.
5. Can I explain every file in it to the class? If the answer is "the AI wrote it and I am not sure", that is
the part to fix before Oct 12.
Question 2 is where most ideas fail, and it is much cheaper to fail it now.
Working with AI on this
You should use Claude, ChatGPT, Gemini or Claude Code to build this. That is the course, not a way around it.
One thing worth knowing before you start. If you open a chat and say "help me build an agent", you will get
something quickly, and there is a real chance it will be one of the three things above that do not count. These
assistants are agreeable. They will reach for a framework you do not need, or hand you a script with an API call
in it, because that is the most common shape of request they see and they have no reason to think your
situation is different.
They do much better when they know what you are being held to. The constraints that matter are all in this
guide: your own code makes the API call, the path varies depending on what it finds, tools return facts, the
judgment stays with the model, no framework, nothing secret in the repository.
How you get those in front of your assistant is up to you.
MiniProject_WhatCountsAsAnAgent.md 2026-10-01
3 / 4
What the repository needs
Your repo is part of the grade.
A README that says what the agent does, what problem it solves, and how to run it.
Sensible structure. Not everything in one file called final_final_v2.py.
Real commit history. Several commits as you built it, not one commit called "upload".
No secrets, ever. Your API key goes in a .env file, and .env goes in .gitignore before your first push.
If a key ever reaches GitHub, deleting the file does not help, because it stays in the history. You rotate
the key.
We cover the .gitignore properly in Class 6 and you will watch a repository get pushed.
Costs
API calls cost money. A small agent doing a handful of steps costs a few cents per run, and developing it
means running it many times. Budget a few dollars for the whole project. Use the cheapest model that can do
your task, which is usually a smaller one, and we compare them live in Class 6.
If cost is a genuine barrier for you, come and talk to me rather than quietly not doing the project.
If you are not sure
Bring me the idea before you build it. One sentence describing the problem and one sentence on what the
agent would do. I will tell you in two minutes whether it needs an agent or a script, and that conversation is
much cheaper than finding out on Oct 10.