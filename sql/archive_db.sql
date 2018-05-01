BEGIN TRANSACTION;

insert into usage_reactions_archive select *, strftime("%Y", date('now','-1 month')) as year, strftime("%m", date('now','-1 month')) as month from usage_reactions;
insert into usage_messages_archive select *, strftime("%Y", date('now','-1 month')) as year, strftime("%m", date('now','-1 month')) as month from usage_messages;
insert into usage_mentions_archive select *, strftime("%Y", date('now','-1 month')) as year, strftime("%m", date('now','-1 month')) as month from usage_mentions;
insert into usage_commands_archive select *, strftime("%Y", date('now','-1 month')) as year, strftime("%m", date('now','-1 month')) as month from usage_commands;

delete from usage_reactions;
delete from usage_messages;
delete from usage_mentions;
delete from usage_commands;

COMMIT;