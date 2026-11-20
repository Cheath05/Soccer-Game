import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { Link, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import {
  useCareer,
  useInternational,
  useMyNation,
  useNationJob,
  useSaveNationSquad,
} from "../api/hooks";
import type { MyNation } from "../api/types";
import { foldText, longDate, positionColor } from "../lib/format";
import ClubLink from "./ClubLink";
import PlayerLink from "./PlayerLink";

const SHOWN = 80; // eligible players listed before a search

/** The International page's "My country" tab (W8 I5): take a national team's job alongside the
 * club, pick its squad for the windows and tournaments, and see its next matches. */
export default function NationManager() {
  const mine = useMyNation();
  if (!mine.data) return null;
  // Keyed by the saved squad, so the picks start again from it after a save.
  const key = mine.data.players
    .filter((p) => p.selected)
    .map((p) => p.id)
    .join(",");
  return mine.data.team ? <Job key={key} data={mine.data} /> : <TakeJob />;
}

/** Take a national team's job; ``move``: a manager without a club moving to another country. */
function TakeJob({ move = false }: { move?: boolean }) {
  const teams = useInternational().data?.teams ?? [];
  const job = useNationJob();
  const [code, setCode] = useState<string | null>(null);
  return (
    <Card withBorder padding="md" maw={560}>
      <Title order={4}>{move ? "Move to another country" : "Manage a country"}</Title>
      <Text size="sm" c="dimmed" mt={4}>
        {move
          ? "Take another national team’s job in place of this one: its squad is picked for you to start with, and its matches become yours."
          : "Take a national team’s job alongside your club. You pick its squad for every international window and tournament, set its tactics, and play its matches as your own: they stop Continue like your club’s."}
      </Text>
      <Group mt="md" align="flex-end">
        <Select
          label="Country"
          searchable
          placeholder="Find a country"
          data={teams.map((t) => ({
            value: t.code,
            label: `${t.team.name} (#${t.rank})`,
          }))}
          value={code}
          onChange={setCode}
          w={300}
        />
        <Button
          disabled={!code}
          loading={job.isPending}
          onClick={() => code && job.mutate(code)}
        >
          Take the job
        </Button>
      </Group>
      {job.error && (
        <Alert color="red" mt="sm">
          {job.error.message}
        </Alert>
      )}
    </Card>
  );
}

function Job({ data }: { data: MyNation }) {
  const job = useNationJob();
  const save = useSaveNationSquad();
  const navigate = useNavigate();
  // A national team's manager without a club: the country is his only team, so no leaving.
  const only = !!useCareer().data?.nation_only;
  const saved = useMemo(
    () => new Set(data.players.filter((p) => p.selected).map((p) => p.id)),
    [data],
  );
  const [chosen, setChosen] = useState<Set<number>>(saved);
  const [search, setSearch] = useState("");
  const changed =
    chosen.size !== saved.size || [...chosen].some((id) => !saved.has(id));
  const needle = foldText(search.trim());
  const listed = data.players.filter((p) =>
    needle ? foldText(p.name).includes(needle) : true,
  );
  const shown = needle
    ? listed
    : [
        ...listed.filter((p) => chosen.has(p.id)),
        ...listed.filter((p) => !chosen.has(p.id)).slice(0, SHOWN),
      ];
  const toggle = (id: number) => {
    const next = new Set(chosen);
    if (next.has(id)) next.delete(id);
    else if (next.size < data.squad_size) next.add(id);
    setChosen(next);
  };
  const team = data.team!;
  return (
    <Stack>
      <Card withBorder padding="sm">
        <Group justify="space-between">
          <div>
            <Title order={4}>
              <ClubLink club={team} />{" "}
              <Badge variant="light">{data.code}</Badge>
            </Title>
            <Text size="sm" c="dimmed">
              You manage {team.name}
              {only ? ", your only team" : " alongside your club"}. Its squad
              stays as you pick it; an empty one is picked for you at the next
              call-up.
            </Text>
          </div>
          <Group gap="xs">
            <Button
              variant="default"
              onClick={() =>
                void navigate({ to: "/tactics", search: { team: "nation" } })
              }
            >
              Tactics
            </Button>
            {!only && (
              <Button
                variant="subtle"
                color="red"
                loading={job.isPending}
                onClick={() => job.mutate(null)}
              >
                Leave the job
              </Button>
            )}
          </Group>
        </Group>
        <Title order={5} mt="sm">
          Next matches
        </Title>
        {data.fixtures.length === 0 ? (
          <Text size="sm" c="dimmed">
            None scheduled yet: friendlies are arranged the day before each
            international window.
          </Text>
        ) : (
          <Stack gap={2}>
            {data.fixtures.map((f) => (
              <Group key={f.id} gap="xs" wrap="nowrap">
                <Text size="sm" c="dimmed" w={110}>
                  {longDate(f.date)}
                </Text>
                <Text size="sm" truncate>
                  <Link
                    to="/match/$fixtureId"
                    params={{ fixtureId: String(f.id) }}
                  >
                    {f.home.name} v {f.away.name}
                  </Link>{" "}
                  <Text span size="xs" c="dimmed">
                    {f.competition_name}
                  </Text>
                </Text>
              </Group>
            ))}
          </Stack>
        )}
      </Card>
      <Card withBorder padding="sm" aria-label="Squad">
        <Group justify="space-between" mb="xs">
          <Title order={4}>
            Squad{" "}
            <Text
              span
              c={
                chosen.size > data.squad_size || chosen.size < 11
                  ? "red"
                  : "dimmed"
              }
              fz="sm"
            >
              {chosen.size} / {data.squad_size}
            </Text>
          </Title>
          <Group gap="xs">
            <TextInput
              size="xs"
              placeholder="Find a player"
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
              aria-label="Find a player"
            />
            <Button
              size="xs"
              variant="default"
              disabled={!changed}
              onClick={() => setChosen(saved)}
            >
              Undo
            </Button>
            <Button
              size="xs"
              disabled={!changed || chosen.size < 11}
              loading={save.isPending}
              onClick={() => save.mutate([...chosen])}
            >
              Save squad
            </Button>
          </Group>
        </Group>
        {save.error && (
          <Alert color="red" mb="xs">
            {save.error.message}
          </Alert>
        )}
        <Table.ScrollContainer minWidth={0}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={36} />
                <Table.Th>Player</Table.Th>
                <Table.Th>Pos</Table.Th>
                <Table.Th ta="right">Age</Table.Th>
                <Table.Th ta="right">Ovr</Table.Th>
                <Table.Th visibleFrom="sm">Club</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {shown.map((p) => (
                <Table.Tr
                  key={p.id}
                  onClick={() => toggle(p.id)}
                  style={{ cursor: "pointer" }}
                >
                  <Table.Td>
                    <Checkbox
                      size="xs"
                      checked={chosen.has(p.id)}
                      onChange={() => toggle(p.id)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Call up ${p.name}`}
                    />
                  </Table.Td>
                  <Table.Td>
                    <PlayerLink player={p} />
                    {p.injured && (
                      <Badge size="xs" color="red" ml={6}>
                        Injured
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Badge size="sm" color={positionColor(p.position)}>
                      {p.position}
                    </Badge>
                  </Table.Td>
                  <Table.Td ta="right" className="fs-num">
                    {p.age}
                  </Table.Td>
                  <Table.Td ta="right" className="fs-num" fw={600}>
                    {p.overall}
                  </Table.Td>
                  <Table.Td visibleFrom="sm">
                    {p.club ? (
                      <ClubLink club={p.club} />
                    ) : (
                      <Text span size="sm" c="dimmed">
                        Home-based
                      </Text>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {!needle && data.players.length > shown.length && (
          <Text size="xs" c="dimmed" mt="xs">
            Your squad and the best {SHOWN} others of {data.players.length}{" "}
            eligible: find a player to see the rest.
          </Text>
        )}
      </Card>
      {only && <TakeJob move />}
    </Stack>
  );
}
